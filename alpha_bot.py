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

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Configurações Reddit API
REDDIT_CLIENT_ID = os.environ.get('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.environ.get('REDDIT_CLIENT_SECRET')
REDDIT_USERNAME = os.environ.get('REDDIT_USERNAME')
REDDIT_PASSWORD = os.environ.get('REDDIT_PASSWORD')

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
            'User-Agent': 'AlphaHunterBot/1.0 by YourUsername',
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
                    logging.info("✅ Reddit API token obtido com sucesso!")
                    return self.access_token
                else:
                    logging.error(f"❌ Erro ao obter token: {response.status}")
                    return None
        except Exception as e:
            logging.error(f"❌ Exception getting token: {e}")
            return None
    
    async def search_posts(self, subreddit, query, limit=25, sort='new'):
        """Busca posts usando API oficial"""
        token = await self.get_access_token()
        if not token:
            return []
        
        headers = {
            'User-Agent': 'AlphaHunterBot/1.0',
            'Authorization': f'Bearer {token}'
        }
        
        url = f'https://oauth.reddit.com/r/{subreddit}/search'
        params = {
            'q': query,
            'sort': sort,
            'limit': limit,
            'restrict_sr': 'on',
            't': 'day'
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
                    logging.error(f"❌ Search error: {response.status}")
                    return []
        except Exception as e:
            logging.error(f"❌ Search exception: {e}")
            return []
    
    async def get_new_posts(self, subreddit, limit=25):
        """Pega posts novos usando API oficial"""
        token = await self.get_access_token()
        if not token:
            return []
        
        headers = {
            'User-Agent': 'AlphaHunterBot/1.0',
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
                    logging.error(f"❌ New posts error: {response.status}")
                    return []
        except Exception as e:
            logging.error(f"❌ New posts exception: {e}")
            return []
    
    def parse_posts(self, data):
        """Parseia os posts da API response"""
        posts = []
        
        if 'data' in data and 'children' in data['data']:
            for child in data['data']['children']:
                post_data = child['data']
                
                posts.append({
                    'title': post_data.get('title', ''),
                    'selftext': post_data.get('selftext', ''),
                    'url': f"https://reddit.com{post_data.get('permalink', '')}",
                    'created_utc': post_data.get('created_utc', 0),
                    'score': post_data.get('score', 0),
                    'num_comments': post_data.get('num_comments', 0),
                    'upvote_ratio': post_data.get('upvote_ratio', 0),
                    'author': post_data.get('author', ''),
                    'subreddit': post_data.get('subreddit', '')
                })
        
        return posts
    
    async def close(self):
        await self.session.close()

class AlphaHunterBot:
    def __init__(self):
        self.reddit_api = RedditAPI()
        self.vistos = set()
        self.keywords = [
            "presale", "launch", "new token", "meme coin",
            "fair launch", "stealth launch", "ido", 
            "initial offering", "token sale", "going live",
            "airdrop", "whitelist", "early access", "gem",
            "moonshot", "100x", "low cap", "hidden gem"
        ]
    
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
            logging.error(f"Erro Telegram: {e}")
            return False
    
    async def monitor_reddit_api(self):
        """Monitora Reddit usando API oficial"""
        posts = []
        subreddits = ["CryptoMoonShots", "CryptoCurrency", "CryptoMars", "CryptoGems"]
        
        for subreddit in subreddits:
            try:
                # Buscar posts novos
                new_posts = await self.reddit_api.get_new_posts(subreddit, limit=15)
                
                # Buscar por keywords
                for keyword in self.keywords:
                    keyword_posts = await self.reddit_api.search_posts(subreddit, keyword, limit=10)
                    new_posts.extend(keyword_posts)
                
                for post in new_posts:
                    text = f"{post['title']} {post['selftext']}".lower()
                    
                    # Verificar se contém keywords importantes
                    found_keywords = []
                    for keyword in self.keywords:
                        if keyword in text:
                            found_keywords.append(keyword)
                    
                    if found_keywords:
                        posts.append({
                            **post,
                            'keywords': found_keywords,
                            'relevance_score': len(found_keywords) + (post['score'] / 100)
                        })
                        
                        logging.info(f"📝 API Found: {post['title'][:50]}...")
                
            except Exception as e:
                logging.error(f"❌ Error monitoring {subreddit}: {e}")
                continue
        
        # Ordenar por relevância
        posts.sort(key=lambda x: x['relevance_score'], reverse=True)
        return posts[:20]  # Top 20 posts
    
    def analyze_reddit_posts(self, posts):
        """Analisa posts do Reddit para oportunidades"""
        opportunities = []
        token_mentions = {}
        
        for post in posts:
            # Detectar padrões de presale
            text = f"{post['title']} {post['selftext']}".lower()
            
            if self.detect_presale_patterns(text):
                opportunities.append({
                    'type': 'PRESALE_ALERT',
                    'title': post['title'],
                    'url': post['url'],
                    'subreddit': post['subreddit'],
                    'keywords': post['keywords'],
                    'score': post['score'],
                    'comments': post['num_comments'],
                    'confidence': 'HIGH'
                })
            
            # Analisar menções de tokens
            tokens = self.extract_tokens(text)
            for token in tokens:
                token_mentions[token] = token_mentions.get(token, 0) + 1
        
        # Adicionar tokens trending
        for token, count in token_mentions.items():
            if count >= 3:  # Mencionado pelo menos 3 vezes
                opportunities.append({
                    'type': 'TRENDING_TOKEN',
                    'token': token,
                    'mentions': count,
                    'source': 'reddit',
                    'confidence': 'MEDIUM'
                })
        
        return opportunities
    
    def detect_presale_patterns(self, text):
        """Detecta padrões de presale"""
        patterns = [
            r'presale.*(live|start|begin)',
            r'launch.*(tomorrow|today|tonight)',
            r'fair.*launch',
            r'stealth.*launch',
            r'token.*sale',
            r'ido.*(starting|live)',
            r'going.*live.*[0-9]',
            r'whitelist.*(open|starting)'
        ]
        
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def extract_tokens(self, text):
        """Extrai tokens mencionados"""
        # Padrões para tokens
        patterns = [
            r'\$([A-Z]{3,6})\b',  # $TOKEN
            r'\b([A-Z]{3,6})\b.*(token|coin|launch)',
            r'(buy|get|trade).*\b([A-Z]{3,6})\b'
        ]
        
        tokens = set()
        for pattern in patterns:
            matches = re.findall(pattern, text.upper())
            for match in matches:
                token = match[0] if isinstance(match, tuple) else match
                if token not in ["ETH", "BTC", "BNB", "USDT", "USDC", "USD"]:
                    tokens.add(token)
        
        return list(tokens)
    
    def create_alpha_message(self, opportunity):
        """Cria mensagem detalhada"""
        if opportunity['type'] == 'PRESALE_ALERT':
            message = f"🚀 <b>PRESALE ALERT - REDDIT API</b>\n\n"
            message += f"📢 <b>{opportunity['title']}</b>\n"
            message += f"🌐 <b>Subreddit:</b> r/{opportunity['subreddit']}\n"
            message += f"⭐ <b>Score:</b> {opportunity['score']} ↑\n"
            message += f"💬 <b>Comments:</b> {opportunity['comments']}\n"
            message += f"🔍 <b>Keywords:</b> {', '.join(opportunity['keywords'][:3])}\n"
            message += f"🔗 <a href='{opportunity['url']}'>Ver post</a>\n\n"
            message += "🎯 <b>OPORTUNIDADE DE ALPHA REAL-TIME!</b>"
            
        elif opportunity['type'] == 'TRENDING_TOKEN':
            message = f"📈 <b>TRENDING TOKEN - REDDIT API</b>\n\n"
            message += f"🏷 <b>Token:</b> {opportunity['token']}\n"
            message += f"🔊 <b>Mentions:</b> {opportunity['mentions']}\n"
            message += f"🌐 <b>Source:</b> Multiple subreddits\n\n"
            message += "📢 <b>Estou sendo muito mencionado!</b>\n"
            message += "🔍 <i>Possível lançamento em breve!</i>"
        
        message += f"\n\n⏰ <i>{datetime.now().strftime('%d/%m %H:%M:%S')}</i>"
        return message
    
    async def run(self):
        """Loop principal com API oficial"""
        logging.info("🤖 Alpha Hunter Bot com API Reddit iniciado!")
        
        self.send_telegram("🚀 <b>Alpha Hunter com API Reddit iniciado!</b>\n🔍 Monitoramento em tempo real\n🎯 Dados estruturados e confiáveis")
        
        while True:
            try:
                # Usar API oficial
                posts = await self.monitor_reddit_api()
                opportunities = self.analyze_reddit_posts(posts)
                
                logging.info(f"📊 Posts analisados: {len(posts)}")
                logging.info(f"🎯 Oportunidades encontradas: {len(opportunities)}")
                
                for opp in opportunities:
                    opp_id = f"{opp['type']}_{opp.get('token', '')}_{opp.get('url', '')}"
                    
                    if opp_id not in self.vistos:
                        self.vistos.add(opp_id)
                        
                        message = self.create_alpha_message(opp)
                        if self.send_telegram(message):
                            logging.info(f"✅ Alpha enviado: {opp['type']}")
                
                # Esperar 2-3 minutos
                wait_time = random.randint(120, 180)
                logging.info(f"⏳ Próxima verificação em {wait_time//60} minutos...")
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                logging.error(f"❌ Erro no loop principal: {e}")
                await asyncio.sleep(60)
    
    async def close(self):
        await self.reddit_api.close()

# Função principal
async def main():
    """Função principal"""
    # Verificar credenciais
    required_vars = ['REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET', 'REDDIT_USERNAME', 'REDDIT_PASSWORD']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        logging.error(f"❌ Variáveis missing: {missing_vars}")
        logging.error("💡 Configure no Render: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD")
        return
    
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logging.error("❌ Configure TELEGRAM_TOKEN e CHAT_ID!")
        return
    
    bot = AlphaHunterBot()
    try:
        await bot.run()
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
