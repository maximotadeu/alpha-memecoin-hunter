import os
import requests
import time
import logging
import random
import re
import aiohttp
import asyncio
from datetime import datetime, timedelta
import base64
import json
from flask import Flask, Response

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurações para Render
PORT = int(os.environ.get("PORT", 10000))
app = Flask(__name__)

# Health check endpoint para Render
@app.route('/')
def home():
    return Response("🤖 Alpha Hunter Bot is running!", status=200)

@app.route('/health')
def health_check():
    return Response("🤖 Alpha Hunter Bot is healthy!", status=200)

# Configurações Reddit API
REDDIT_CLIENT_ID = os.environ.get('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.environ.get('REDDIT_CLIENT_SECRET')
REDDIT_USERNAME = os.environ.get('REDDIT_USERNAME')
REDDIT_PASSWORD = os.environ.get('REDDIT_PASSWORD')
REDDIT_USER_AGENT = os.environ.get('REDDIT_USER_AGENT', 'AlphaHunterBot/1.0 by YourUsername')

# Configurações Twitter API
TWITTER_BEARER_TOKEN = os.environ.get('TWITTER_BEARER_TOKEN')

# Configurações Telegram
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

class RedditAPI:
    def __init__(self):
        self.access_token = None
        self.token_expiry = None
        self.session = aiohttp.ClientSession()
        self.banned_subreddits = set()
    
    async def get_access_token(self):
        """Obtém access token da API do Reddit"""
        if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.access_token
        
        auth = base64.b64encode(f"{REDDIT_CLIENT_ID}:{REDDIT_CLIENT_SECRET}".encode()).decode()
        
        headers = {
            'User-Agent': REDDIT_USER_AGENT,
            'Authorization': f'Basic {auth}'
        }
        
        data = {
            'grant_type': 'password',
            'username': REDDIT_USERNAME,
            'password': REDDIT_PASSWORD
        }
        
        try:
            async with self.session.post(
                'https://www.reddit.com/api/v1/access_token',
                headers=headers,
                data=data,
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    self.access_token = result['access_token']
                    self.token_expiry = datetime.now() + timedelta(seconds=result['expires_in'] - 60)
                    logger.info("✅ Reddit API token obtido com sucesso!")
                    return self.access_token
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Erro ao obter token: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"❌ Exception getting token: {e}")
            return None
    
    async def search_posts(self, subreddit, query, limit=20):
        """Busca posts usando API oficial"""
        if subreddit in self.banned_subreddits:
            return []
            
        token = await self.get_access_token()
        if not token:
            return []
        
        headers = {
            'User-Agent': REDDIT_USER_AGENT,
            'Authorization': f'Bearer {token}'
        }
        
        url = f'https://oauth.reddit.com/search'
        params = {
            'q': f'subreddit:{subreddit} {query}',
            'sort': 'new',
            'limit': min(limit, 15),
            't': 'day',
            'type': 'link'
        }
        
        try:
            async with self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=15
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return self.parse_posts(data)
                elif response.status == 404:
                    logger.warning(f"⚠️  Subreddit r/{subreddit} banado/privado")
                    self.banned_subreddits.add(subreddit)
                    return []
                else:
                    return []
        except Exception as e:
            logger.error(f"❌ Search exception: {e}")
            return []
    
    async def get_new_posts(self, subreddit, limit=20):
        """Pega posts novos usando API oficial"""
        if subreddit in self.banned_subreddits:
            return []
            
        token = await self.get_access_token()
        if not token:
            return []
        
        headers = {
            'User-Agent': REDDIT_USER_AGENT,
            'Authorization': f'Bearer {token}'
        }
        
        url = f'https://oauth.reddit.com/r/{subreddit}/new'
        params = {'limit': min(limit, 15)}
        
        try:
            async with self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=15
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return self.parse_posts(data)
                elif response.status == 404:
                    logger.warning(f"⚠️  Subreddit r/{subreddit} banado/privado")
                    self.banned_subreddits.add(subreddit)
                    return []
                else:
                    return []
        except Exception as e:
            logger.error(f"❌ New posts exception: {e}")
            return []
    
    def parse_posts(self, data):
        """Parseia os posts da API response"""
        posts = []
        
        if 'data' in data and 'children' in data['data']:
            for child in data['data']['children']:
                post_data = child['data']
                
                if not post_data.get('stickied') and not post_data.get('over_18'):
                    posts.append({
                        'title': post_data.get('title', ''),
                        'selftext': post_data.get('selftext', ''),
                        'url': f"https://reddit.com{post_data.get('permalink', '')}",
                        'created_utc': post_data.get('created_utc', 0),
                        'score': post_data.get('score', 0),
                        'num_comments': post_data.get('num_comments', 0),
                        'upvote_ratio': post_data.get('upvote_ratio', 0),
                        'author': post_data.get('author', ''),
                        'subreddit': post_data.get('subreddit', ''),
                        'id': post_data.get('id', ''),
                        'source': 'reddit'
                    })
        
        return posts
    
    async def close(self):
        await self.session.close()

class TwitterAPI:
    def __init__(self):
        self.session = aiohttp.ClientSession()
        self.last_request_time = 0
        self.rate_limit_remaining = 450
        self.rate_limit_reset = 0
        self.request_count = 0
        self.rate_limit_wait_time = 0
    
    async def handle_rate_limit(self):
        """Gerencia rate limit do Twitter de forma mais robusta"""
        current_time = time.time()
        
        # Se estamos em período de espera por rate limit
        if self.rate_limit_wait_time > current_time:
            wait_remaining = self.rate_limit_wait_time - current_time
            logger.warning(f"🐦 Rate limit Twitter - Aguardando {wait_remaining:.0f}s")
            await asyncio.sleep(wait_remaining)
            self.rate_limit_remaining = 450
            self.rate_limit_wait_time = 0
            return True
        
        # Verificar se estamos perto do limite
        if self.rate_limit_remaining <= 10:
            logger.warning(f"🐦 Rate limit baixo: {self.rate_limit_remaining} requests restantes")
            # Esperar estratégicamente antes de fazer mais requests
            await asyncio.sleep(30)
            return True
        
        # Espera mínima entre requests para evitar rate limiting
        time_since_last = current_time - self.last_request_time
        if time_since_last < 3.0:
            await asyncio.sleep(3.0 - time_since_last)
        
        return False
    
    async def search_tweets(self, query, limit=10):
        """Busca tweets usando API v2 do Twitter - MELHORADO"""
        if not TWITTER_BEARER_TOKEN:
            return []
        
        # Verificar rate limit antes de prosseguir
        if await self.handle_rate_limit():
            return []
        
        headers = {
            'Authorization': f'Bearer {TWITTER_BEARER_TOKEN}'
        }
        
        # Query otimizada para crypto
        optimized_query = f'({query}) (crypto OR cryptocurrency OR blockchain OR defi OR nft) -is:retweet lang:en'
        
        url = 'https://api.twitter.com/2/tweets/search/recent'
        params = {
            'query': optimized_query,
            'max_results': min(limit, 30),  # Reduzido para evitar rate limiting
            'tweet.fields': 'created_at,public_metrics,author_id,context_annotations',
            'expansions': 'author_id',
            'user.fields': 'username,name,verified',
            'media.fields': 'url'
        }
        
        try:
            start_time = time.time()
            async with self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=25
            ) as response:
                self.last_request_time = time.time()
                self.request_count += 1
                
                # Atualizar métricas de rate limit
                if 'x-rate-limit-remaining' in response.headers:
                    self.rate_limit_remaining = int(response.headers['x-rate-limit-remaining'])
                if 'x-rate-limit-reset' in response.headers:
                    reset_time = int(response.headers['x-rate-limit-reset'])
                    self.rate_limit_reset = reset_time
                
                response_time = time.time() - start_time
                
                if response.status == 200:
                    data = await response.json()
                    tweets = self.parse_tweets(data)
                    logger.info(f"🐦 Twitter: {len(tweets)} tweets em {response_time:.2f}s")
                    return tweets
                
                elif response.status == 429:
                    # Rate limit excedido - calcular tempo de espera
                    reset_time = int(response.headers.get('x-rate-limit-reset', time.time() + 900))
                    wait_time = max(reset_time - time.time(), 60)
                    self.rate_limit_wait_time = time.time() + wait_time
                    
                    logger.warning(f"🐦 Rate limit excedido! Aguardando {wait_time:.0f}s")
                    return []
                
                elif response.status == 400:
                    error_data = await response.json()
                    logger.warning(f"🐦 Twitter query error: {error_data.get('detail', 'Unknown')}")
                    return []
                
                else:
                    logger.warning(f"🐦 Twitter error {response.status}")
                    return []
                    
        except asyncio.TimeoutError:
            logger.warning("🐦 Twitter timeout - pulando busca")
            return []
        except Exception as e:
            logger.error(f"🐦 Twitter exception: {e}")
            return []
    
    def parse_tweets(self, data):
        """Parseia os tweets da API response"""
        tweets = []
        
        if 'data' in data and isinstance(data['data'], list):
            users = {}
            if 'includes' in data and 'users' in data['includes']:
                for user in data['includes']['users']:
                    users[user['id']] = user
            
            for tweet_data in data['data']:
                author_id = tweet_data.get('author_id')
                author_info = users.get(author_id, {})
                
                # Filtrar tweets com baixo engajamento (critério mais relaxado)
                metrics = tweet_data.get('public_metrics', {})
                if metrics.get('like_count', 0) + metrics.get('retweet_count', 0) < 2:
                    continue
                
                tweets.append({
                    'text': tweet_data.get('text', ''),
                    'url': f"https://twitter.com/{author_info.get('username', '')}/status/{tweet_data.get('id', '')}",
                    'created_at': tweet_data.get('created_at', ''),
                    'likes': metrics.get('like_count', 0),
                    'retweets': metrics.get('retweet_count', 0),
                    'replies': metrics.get('reply_count', 0),
                    'author': author_info.get('username', ''),
                    'author_name': author_info.get('name', ''),
                    'verified': author_info.get('verified', False),
                    'id': tweet_data.get('id', ''),
                    'source': 'twitter'
                })
        
        return tweets
    
    async def close(self):
        await self.session.close()

class AlphaHunterBot:
    def __init__(self):
        self.reddit_api = RedditAPI()
        self.twitter_api = TwitterAPI()
        self.vistos = set()
        self.keywords = [
            "presale", "launch", "new token", "meme coin",
            "fair launch", "stealth launch", "ido", 
            "initial offering", "token sale", "going live",
            "airdrop", "whitelist", "early access", "gem",
            "moonshot", "100x", "low cap", "hidden gem",
            "#presale", "#launch", "#airdrop", "#ido"
        ]
        self.safe_subreddits = [
            "CryptoCurrency", "CryptoMarkets", "defi",
            "ethereum", "binance", "Crypto_General",
            "NFT", "BlockchainStartups", "CryptoTechnology",
            "altcoin", "cryptomooncalls"
        ]
        self.twitter_cycle = 0
    
    def send_telegram(self, message):
        """Envia mensagem para Telegram"""
        if not TELEGRAM_TOKEN or not CHAT_ID:
            return False
            
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID, 
            "text": message, 
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"❌ Erro Telegram: {e}")
            return False
    
    async def monitor_reddit(self):
        """Monitora Reddit usando API oficial"""
        posts = []
        
        for subreddit in self.safe_subreddits:
            try:
                # Buscar posts novos
                new_posts = await self.reddit_api.get_new_posts(subreddit, limit=10)
                
                # Buscar por keywords específicas
                for keyword in random.sample(self.keywords, min(3, len(self.keywords))):
                    keyword_posts = await self.reddit_api.search_posts(subreddit, keyword, limit=5)
                    new_posts.extend(keyword_posts)
                    await asyncio.sleep(1)  # Aumentado para reduzir rate limiting
                
                for post in new_posts:
                    post_id = f"reddit_{post.get('id', '')}"
                    if post_id in self.vistos:
                        continue
                    
                    self.vistos.add(post_id)
                    
                    text = f"{post['title']} {post['selftext']}".lower()
                    
                    # Verificar keywords
                    found_keywords = []
                    for keyword in self.keywords:
                        if keyword.lower() in text:
                            found_keywords.append(keyword)
                    
                    if found_keywords and post['score'] >= 2:
                        posts.append({
                            **post,
                            'keywords': found_keywords,
                            'relevance_score': len(found_keywords) + (post['score'] / 50) + (post['num_comments'] / 20)
                        })
                        
                        logger.info(f"📝 Reddit: {post['title'][:60]}...")
                
                await asyncio.sleep(2)  # Aumentado para reduzir rate limiting
                
            except Exception as e:
                logger.error(f"❌ Error monitoring Reddit: {e}")
                continue
        
        return posts
    
    async def monitor_twitter(self):
        """Monitora Twitter para oportunidades - MELHORADO"""
        tweets = []
        
        if not TWITTER_BEARER_TOKEN:
            return tweets
        
        # Buscar no Twitter a cada 3 ciclos para reduzir rate limiting
        self.twitter_cycle += 1
        if self.twitter_cycle % 3 != 0:
            logger.info("🐦 Twitter: Pulando ciclo para reduzir rate limiting")
            return tweets
        
        try:
            # Grupos de keywords otimizados (menos frequentes)
            keyword_groups = [
                "presale OR launch OR token OR airdrop",
                "whitelist OR ido OR gem OR moonshot"
            ]
            
            for query in keyword_groups:
                found_tweets = await self.twitter_api.search_tweets(query, limit=8)  # Reduzido
                
                for tweet in found_tweets:
                    tweet_id = f"twitter_{tweet.get('id', '')}"
                    if tweet_id in self.vistos:
                        continue
                    
                    self.vistos.add(tweet_id)
                    
                    text = tweet['text'].lower()
                    
                    found_keywords = []
                    for kw in self.keywords:
                        if kw.lower() in text:
                            found_keywords.append(kw)
                    
                    if found_keywords and tweet['likes'] >= 3:  # Critério mais relaxado
                        tweets.append({
                            **tweet,
                            'keywords': found_keywords,
                            'relevance_score': len(found_keywords) + (tweet['likes'] / 100) + (tweet['retweets'] / 50)
                        })
                        
                        logger.info(f"🐦 Twitter: {tweet['text'][:60]}...")
                
                await asyncio.sleep(5)  # Aumentado para reduzir rate limiting
            
        except Exception as e:
            logger.error(f"❌ Error monitoring Twitter: {e}")
        
        return tweets
    
    async def monitor_sources(self):
        """Monitora todas as fontes"""
        try:
            reddit_posts, twitter_tweets = await asyncio.gather(
                self.monitor_reddit(),
                self.monitor_twitter(),
                return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(reddit_posts, Exception):
                logger.error(f"Reddit monitoring failed: {reddit_posts}")
                reddit_posts = []
            if isinstance(twitter_tweets, Exception):
                logger.error(f"Twitter monitoring failed: {twitter_tweets}")
                twitter_tweets = []
            
            all_content = reddit_posts + twitter_tweets
            all_content.sort(key=lambda x: x['relevance_score'], reverse=True)
            
            logger.info(f"📊 Reddit: {len(reddit_posts)}, Twitter: {len(twitter_tweets)}")
            return all_content[:20]  # Reduzido
            
        except Exception as e:
            logger.error(f"❌ Error in monitor_sources: {e}")
            return []
    
    def analyze_content(self, content_list):
        """Analisa conteúdos para oportunidades"""
        opportunities = []
        token_mentions = {}
        
        for content in content_list:
            text = ""
            if content['source'] == 'reddit':
                text = f"{content['title']} {content['selftext']}".lower()
            else:
                text = content['text'].lower()
            
            # Detectar padrões de presale
            if self.detect_presale_patterns(text):
                opportunities.append({
                    'type': 'PRESALE_ALERT',
                    'title': content.get('title', content.get('text', '')[:100]),
                    'url': content['url'],
                    'source': content['source'],
                    'keywords': content['keywords'],
                    'score': content.get('score', content.get('likes', 0)),
                    'comments': content.get('num_comments', content.get('replies', 0)),
                    'confidence': 'HIGH',
                    'id': content['id']
                })
            
            # Analisar menções de tokens
            tokens = self.extract_tokens(text)
            for token in tokens:
                token_mentions[token] = token_mentions.get(token, 0) + 1
        
        # Adicionar tokens trending
        for token, count in token_mentions.items():
            if count >= 2:
                opportunities.append({
                    'type': 'TRENDING_TOKEN',
                    'token': token,
                    'mentions': count,
                    'source': 'multiple',
                    'confidence': 'MEDIUM',
                    'id': f"token_{token}"
                })
        
        return opportunities
    
    def detect_presale_patterns(self, text):
        """Detecta padrões de presale"""
        patterns = [
            r'presale.*(live|start|begin|active|now)',
            r'launch.*(tomorrow|today|tonight|soon|live)',
            r'fair.*launch',
            r'stealth.*launch',
            r'token.*sale',
            r'ido.*(starting|live|open|register)',
            r'going.*live.*[0-9]',
            r'whitelist.*(open|starting|join|register)',
            r'airdrop.*(claim|live|participate|join)',
            r'early.*access.*(open|available)'
        ]
        
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def extract_tokens(self, text):
        """Extrai tokens mencionados"""
        patterns = [
            r'\$([A-Z]{2,8})\b',
            r'\b([A-Z]{3,8})\b.*(token|coin|launch|presale)',
            r'(buy|get|trade).*\b([A-Z]{3,8})\b'
        ]
        
        tokens = set()
        for pattern in patterns:
            matches = re.findall(pattern, text.upper())
            for match in matches:
                if isinstance(match, tuple):
                    token = match[0] if len(match) > 0 and match[0] else (match[1] if len(match) > 1 else '')
                else:
                    token = match
                
                if (token and len(token) >= 2 and 
                    token not in ["ETH", "BTC", "BNB", "USDT", "USDC", "USD", "THE", "AND", "FOR", "YOU"]):
                    tokens.add(token)
        
        return list(tokens)
    
    def create_alpha_message(self, opportunity):
        """Cria mensagem detalhada"""
        if opportunity['type'] == 'PRESALE_ALERT':
            source_emoji = "🐦" if opportunity['source'] == 'twitter' else "🌐"
            message = f"🚀 <b>PRESALE ALERT - {opportunity['source'].upper()}</b>\n\n"
            message += f"{source_emoji} <b>{opportunity['title']}</b>\n"
            message += f"🔗 <a href='{opportunity['url']}'>Ver conteúdo</a>\n"
            message += f"⭐ <b>Engajamento:</b> {opportunity['score']} ↑\n"
            if opportunity['source'] == 'reddit':
                message += f"💬 <b>Comentários:</b> {opportunity['comments']}\n"
            message += f"🔍 <b>Keywords:</b> {', '.join(opportunity['keywords'][:3])}\n\n"
            message += "🎯 <b>OPORTUNIDADE DE ALPHA REAL-TIME!</b>"
            
        elif opportunity['type'] == 'TRENDING_TOKEN':
            message = f"📈 <b>TRENDING TOKEN - MULTIPLE SOURCES</b>\n\n"
            message += f"🏷 <b>Token:</b> ${opportunity['token']}\n"
            message += f"🔊 <b>Mentions:</b> {opportunity['mentions']}\n"
            message += f"🌐 <b>Source:</b> {opportunity['source']}\n\n"
            message += "📢 <b>Estou sendo muito mencionado!</b>\n"
            message += "🔍 <i>Possível lançamento em breve!</i>"
        
        message += f"\n\n⏰ <i>{datetime.now().strftime('%d/%m %H:%M:%S')}</i>"
        return message
    
    async def run(self):
        """Loop principal"""
        logger.info("🤖 Alpha Hunter Bot com Reddit + Twitter iniciado!")
        
        self.send_telegram("🚀 <b>Alpha Hunter com Reddit + Twitter iniciado!</b>\n🔍 Monitoramento em tempo real\n🎯 Dados de múltiplas fontes")
        
        while True:
            try:
                content = await self.monitor_sources()
                opportunities = self.analyze_content(content)
                
                logger.info(f"📊 Conteúdos analisados: {len(content)}")
                logger.info(f"🎯 Oportunidades encontradas: {len(opportunities)}")
                
                for opp in opportunities:
                    opp_id = f"{opp['type']}_{opp.get('id', '')}"
                    
                    if opp_id not in self.vistos:
                        self.vistos.add(opp_id)
                        
                        message = self.create_alpha_message(opp)
                        if self.send_telegram(message):
                            logger.info(f"✅ Alpha enviado: {opp['type']} from {opp.get('source', 'unknown')}")
                        await asyncio.sleep(1)
                
                # Intervalo adaptativo baseado no número de oportunidades
                base_wait = 180  # 3 minutos
                if opportunities:
                    base_wait = max(120, base_wait - len(opportunities) * 15)
                
                wait_time = random.randint(base_wait, base_wait + 60)
                logger.info(f"⏳ Próxima verificação em {wait_time//60} minutos...")
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"❌ Erro no loop principal: {e}")
                await asyncio.sleep(60)
    
    async def close(self):
        await self.reddit_api.close()
        await self.twitter_api.close()

# Função principal
async def main():
    """Função principal"""
    # Verificar credenciais
    required_vars = ['REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET', 'REDDIT_USERNAME', 'REDDIT_PASSWORD']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        logger.error(f"❌ Variáveis missing: {missing_vars}")
    
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("❌ Configure TELEGRAM_TOKEN e CHAT_ID!")
    
    if not TWITTER_BEARER_TOKEN:
        logger.warning("⚠️  TWITTER_BEARER_TOKEN não configurado")
    
    bot = AlphaHunterBot()
    try:
        # Iniciar o bot em background
        bot_task = asyncio.create_task(bot.run())
        
        # Manter a aplicação rodando
        while True:
            await asyncio.sleep(3600)  # Sleep por 1 hora
            
    except KeyboardInterrupt:
        logger.info("🤖 Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    # Iniciar serv Flask em thread separada para Render
    import threading
    def run_flask():
        app.run(host='0.0.0.0', port=PORT, debug=False)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Executar o bot principal
    asyncio.run(main())
