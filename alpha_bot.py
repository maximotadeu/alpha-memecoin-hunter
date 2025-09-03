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

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
                    logger.error(f"❌ Erro ao obter token: {response.status} - {error_text}")
                    return None
        except Exception as e:
            logger.error(f"❌ Exception getting token: {e}")
            return None
    
    async def search_posts(self, subreddit, query, limit=25, sort='new'):
        """Busca posts usando API oficial"""
        token = await self.get_access_token()
        if not token:
            return []
        
        headers = {
            'User-Agent': REDDIT_USER_AGENT,
            'Authorization': f'Bearer {token}'
        }
        
        url = f'https://oauth.reddit.com/r/{subreddit}/search'
        params = {
            'q': query,
            'sort': sort,
            'limit': limit,
            'restrict_sr': 'on',
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
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Search error: {response.status} - {error_text}")
                    return []
        except Exception as e:
            logger.error(f"❌ Search exception: {e}")
            return []
    
    async def get_new_posts(self, subreddit, limit=25):
        """Pega posts novos usando API oficial"""
        token = await self.get_access_token()
        if not token:
            return []
        
        headers = {
            'User-Agent': REDDIT_USER_AGENT,
            'Authorization': f'Bearer {token}'
        }
        
        url = f'https://oauth.reddit.com/r/{subreddit}/new'
        params = {'limit': limit}
        
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
                else:
                    error_text = await response.text()
                    logger.error(f"❌ New posts error: {response.status} - {error_text}")
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
                
                if post_data.get('is_self') or not post_data.get('stickied'):
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
        self.last_tweet_time = {}
    
    async def search_tweets(self, query, limit=10):
        """Busca tweets usando API v2 do Twitter"""
        if not TWITTER_BEARER_TOKEN:
            logger.error("❌ Twitter Bearer Token não configurado!")
            return []
        
        headers = {
            'Authorization': f'Bearer {TWITTER_BEARER_TOKEN}'
        }
        
        url = 'https://api.twitter.com/2/tweets/search/recent'
        params = {
            'query': f'{query} -is:retweet lang:en',
            'max_results': limit,
            'tweet.fields': 'created_at,public_metrics,author_id',
            'expansions': 'author_id',
            'user.fields': 'username,name'
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
                    return self.parse_tweets(data)
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Twitter search error: {response.status} - {error_text}")
                    return []
        except Exception as e:
            logger.error(f"❌ Twitter search exception: {e}")
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
                
                tweets.append({
                    'text': tweet_data.get('text', ''),
                    'url': f"https://twitter.com/{author_info.get('username', '')}/status/{tweet_data.get('id', '')}",
                    'created_at': tweet_data.get('created_at', ''),
                    'likes': tweet_data.get('public_metrics', {}).get('like_count', 0),
                    'retweets': tweet_data.get('public_metrics', {}).get('retweet_count', 0),
                    'replies': tweet_data.get('public_metrics', {}).get('reply_count', 0),
                    'author': author_info.get('username', ''),
                    'author_name': author_info.get('name', ''),
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
    
    def send_telegram(self, message):
        """Envia mensagem para Telegram"""
        if not TELEGRAM_TOKEN or not CHAT_ID:
            logger.error("❌ Telegram token ou chat ID não configurados!")
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
            if response.status_code == 200:
                return True
            else:
                logger.error(f"❌ Erro Telegram: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Erro Telegram: {e}")
            return False
    
    async def monitor_reddit(self):
        """Monitora Reddit usando API oficial"""
        posts = []
        subreddits = ["CryptoMoonShots", "CryptoCurrency", "CryptoMars", "CryptoGems", "altcoin"]
        
        for subreddit in subreddits:
            try:
                # Buscar posts novos
                new_posts = await self.reddit_api.get_new_posts(subreddit, limit=10)
                
                # Buscar por keywords
                for keyword in self.keywords:
                    keyword_posts = await self.reddit_api.search_posts(subreddit, keyword, limit=5)
                    new_posts.extend(keyword_posts)
                
                for post in new_posts:
                    post_id = post.get('id', '')
                    if post_id in self.vistos:
                        continue
                    
                    self.vistos.add(post_id)
                    
                    text = f"{post['title']} {post['selftext']}".lower()
                    
                    # Verificar se contém keywords importantes
                    found_keywords = []
                    for keyword in self.keywords:
                        if keyword.lower() in text:
                            found_keywords.append(keyword)
                    
                    if found_keywords:
                        posts.append({
                            **post,
                            'keywords': found_keywords,
                            'relevance_score': len(found_keywords) + (post['score'] / 100) + (post['num_comments'] / 10)
                        })
                        
                        logger.info(f"📝 Reddit Found: {post['title'][:50]}...")
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Error monitoring Reddit {subreddit}: {e}")
                continue
        
        return posts
    
    async def monitor_twitter(self):
        """Monitora Twitter para oportunidades"""
        tweets = []
        
        try:
            for keyword in self.keywords:
                if keyword.startswith('#'):
                    search_query = f"{keyword} (crypto OR token OR presale OR launch)"
                else:
                    search_query = f"{keyword} (crypto OR token OR presale OR launch)"
                
                found_tweets = await self.twitter_api.search_tweets(search_query, limit=5)
                
                for tweet in found_tweets:
                    tweet_id = tweet.get('id', '')
                    if tweet_id in self.vistos:
                        continue
                    
                    self.vistos.add(tweet_id)
                    
                    text = tweet['text'].lower()
                    
                    # Verificar se contém keywords importantes
                    found_keywords = []
                    for kw in self.keywords:
                        if kw.lower() in text:
                            found_keywords.append(kw)
                    
                    if found_keywords:
                        tweets.append({
                            **tweet,
                            'keywords': found_keywords,
                            'relevance_score': len(found_keywords) + (tweet['likes'] / 100) + (tweet['retweets'] / 50)
                        })
                        
                        logger.info(f"🐦 Twitter Found: {tweet['text'][:50]}...")
                
                await asyncio.sleep(2)  # Respeitar rate limiting do Twitter
            
        except Exception as e:
            logger.error(f"❌ Error monitoring Twitter: {e}")
        
        return tweets
    
    async def monitor_sources(self):
        """Monitora todas as fontes (Reddit + Twitter)"""
        reddit_posts = await self.monitor_reddit()
        twitter_tweets = await self.monitor_twitter()
        
        all_content = reddit_posts + twitter_tweets
        all_content.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return all_content[:30]  # Top 30 conteúdos
    
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
            r'presale.*(live|start|begin|active)',
            r'launch.*(tomorrow|today|tonight|soon)',
            r'fair.*launch',
            r'stealth.*launch',
            r'token.*sale',
            r'ido.*(starting|live|open)',
            r'going.*live.*[0-9]',
            r'whitelist.*(open|starting|join)',
            r'airdrop.*(claim|live|participate)'
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
                
                if token and len(token) >= 2 and token not in ["ETH", "BTC", "BNB", "USDT", "USDC", "USD", "THE", "AND", "FOR"]:
                    tokens.add(token)
        
        return list(tokens)
    
    def create_alpha_message(self, opportunity):
        """Cria mensagem detalhada"""
        if opportunity['type'] == 'PRESALE_ALERT':
            source_emoji = "📱" if opportunity['source'] == 'twitter' else "🌐"
            message = f"🚀 <b>PRESALE ALERT - {opportunity['source'].upper()}</b>\n\n"
            message += f"{source_emoji} <b>{opportunity['title']}</b>\n"
            message += f"🔗 <a href='{opportunity['url']}'>Ver conteúdo</a>\n"
            message += f"⭐ <b>Engajamento:</b> {opportunity['score']} ↑\n"
            message += f"💬 <b>Interações:</b> {opportunity['comments']}\n"
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
                # Monitorar todas as fontes
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
                
                # Esperar 2-3 minutos
                wait_time = random.randint(120, 180)
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
        logger.error("💡 Configure no Render: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD")
    
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("❌ Configure TELEGRAM_TOKEN e CHAT_ID!")
    
    # Twitter é opcional mas recomendado
    if not TWITTER_BEARER_TOKEN:
        logger.warning("⚠️  TWITTER_BEARER_TOKEN não configurado - monitoramento do Twitter desativado")
    
    bot = AlphaHunterBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("🤖 Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
