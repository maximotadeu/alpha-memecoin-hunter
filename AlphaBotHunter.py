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

# Importar a biblioteca do Google Cloud
from google.cloud import language_v1

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

# Configurações do Bot
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', 300))
URGENCY_THRESHOLD = int(os.environ.get('URGENCY_THRESHOLD', 40))

# Adicione esta classe para análise de sentimento
class SentimentAnalyzer:
    def __init__(self):
        try:
            self.client = language_v1.LanguageServiceClient()
            logger.info("✅ Google Cloud Natural Language API client inicializado.")
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar o cliente do Google Cloud: {e}")
            self.client = None

    def analyze_sentiment(self, text):
        if not self.client or not text:
            return {"score": 0, "magnitude": 0, "error": True}
        
        # Limita o texto para evitar custos excessivos
        truncated_text = text[:1000]

        document = language_v1.Document(content=truncated_text, type_=language_v1.Document.Type.PLAIN_TEXT)
        
        try:
            sentiment = self.client.analyze_sentiment(document=document).document_sentiment
            return {
                "score": sentiment.score,
                "magnitude": sentiment.magnitude,
                "error": False
            }
        except Exception as e:
            logger.error(f"❌ Erro ao analisar sentimento: {e}")
            return {"score": 0, "magnitude": 0, "error": True}

class RedditAPI:
    def __init__(self):
        self.access_token = None
        self.token_expiry = None
        self.session = aiohttp.ClientSession()
        self.banned_subreddits = set()
    
    async def get_access_token(self):
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
        current_time = time.time()
        
        if self.rate_limit_wait_time > current_time:
            wait_remaining = self.rate_limit_wait_time - current_time
            logger.warning(f"🐦 Rate limit Twitter - Aguardando {wait_remaining:.0f}s")
            await asyncio.sleep(wait_remaining)
            self.rate_limit_remaining = 450
            self.rate_limit_wait_time = 0
            return True
        
        if self.rate_limit_remaining <= 10:
            logger.warning(f"🐦 Rate limit baixo: {self.rate_limit_remaining} requests restantes")
            await asyncio.sleep(30)
            return True
        
        time_since_last = current_time - self.last_request_time
        if time_since_last < 3.0:
            await asyncio.sleep(3.0 - time_since_last)
        
        return False
    
    async def search_tweets(self, query, limit=10):
        if not TWITTER_BEARER_TOKEN:
            return []
        
        if await self.handle_rate_limit():
            return []
        
        headers = {
            'Authorization': f'Bearer {TWITTER_BEARER_TOKEN}'
        }
        
        optimized_query = f'({query}) (crypto OR cryptocurrency OR blockchain OR defi OR nft) -is:retweet lang:en'
        
        url = 'https://api.twitter.com/2/tweets/search/recent'
        params = {
            'query': optimized_query,
            'max_results': min(limit, 30),
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
        tweets = []
        if 'data' in data and isinstance(data['data'], list):
            users = {}
            if 'includes' in data and 'users' in data['includes']:
                for user in data['includes']['users']:
                    users[user['id']] = user
            
            for tweet_data in data['data']:
                author_id = tweet_data.get('author_id')
                author_info = users.get(author_id, {})
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
        self.sentiment_analyzer = SentimentAnalyzer()
        self.vistos = set()
        
        self.memecoin_keywords = [
            "meme coin", "memecoin", "dog coin", "cat coin",
            "animal coin", "next shib", "next doge", "next pepe",
            "1000x", "10000x", "moonshot", "gem hunting",
            "stealth launch", "fair launch", "no dev tax",
            "lp locked", "contract renounced", "community owned",
            "#memecoin", "#1000xgem", "#moonshot"
        ]
        
        self.launch_keywords = [
            "launching in", "going live in", "presale in",
            "starting in", "countdown", "t-minus", "in minutes",
            "in hours", "at ", "UTC", "GMT", "EST", "PST"
        ]
        
        self.general_keywords = [
            "presale", "launch", "new token", "meme coin",
            "fair launch", "stealth launch", "ido", 
            "initial offering", "token sale", "going live",
            "airdrop", "whitelist", "early access", "gem",
            "moonshot", "100x", "low cap", "hidden gem",
            "#presale", "#launch", "#airdrop", "#ido"
        ]
        
        self.keywords = list(set(self.general_keywords + self.memecoin_keywords + self.launch_keywords))
        
        self.safe_subreddits = [
            "CryptoCurrency", "CryptoMarkets", "defi",
            "ethereum", "binance", "Crypto_General",
            "NFT", "BlockchainStartups", "CryptoTechnology",
            "altcoin", "cryptomooncalls"
        ]
        
        self.memecoin_subreddits = [
            "memecoin", "Memecoins", "shitcoinmoonshots", 
            "CryptoMoonShots", "cryptomoonshots", "AllCryptoBets",
            "CryptoCurrencyTrading", "cryptostreetbets"
        ]
        
        self.all_subreddits = list(set(self.safe_subreddits + self.memecoin_subreddits))
        
        self.twitter_cycle = 0
    
    def detect_imminent_launch(self, text):
        time_patterns = [
            r'(launch|presale|going live).*(in\s+\d+\s*(hours|hrs|h|minutes|mins|m))',
            r'(in\s+\d+\s*(hours|hrs|h|minutes|mins|m)).*(launch|presale|going live)',
            r'(today|tonight|this (evening|afternoon|morning)|soon).*(launch|presale)',
            r'(launch|presale).*(today|tonight|this (evening|afternoon|morning)|soon)',
            r'\b(\d{1,2}:\d{2}\s*(AM|PM|UTC|GMT)?)\b.*(launch|presale|live)',
            r'(launch|presale|live).*\b(\d{1,2}:\d{2}\s*(AM|PM|UTC|GMT)?)\b'
        ]
        
        for pattern in time_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def extract_launch_time(self, text):
        time_matches = re.findall(r'in\s+(\d+)\s*(hours|hrs|h|minutes|mins|m)', text, re.IGNORECASE)
        specific_time = re.findall(r'\b(\d{1,2}:\d{2})\s*(AM|PM|UTC|GMT)?\b', text, re.IGNORECASE)
        
        time_info = {}
        
        if time_matches:
            amount, unit = time_matches[0]
            amount = int(amount)
            if 'hour' in unit.lower() or 'h' in unit.lower():
                time_info['estimated_hours'] = amount
            else:
                time_info['estimated_minutes'] = amount
        
        if specific_time:
            time_info['specific_time'] = specific_time[0][0] + (f" {specific_time[0][1]}" if specific_time[0][1] else "")
        
        return time_info

    def calculate_urgency_score(self, content):
        if content['source'] == 'reddit':
            text = content['title'] + " " + content.get('selftext', '')
            post_time = datetime.fromtimestamp(content.get('created_utc', time.time()))
        else:
            text = content.get('text', '')
            try:
                post_time = datetime.strptime(content.get('created_at', ''), '%Y-%m-%dT%H:%M:%S.%fZ')
            except:
                post_time = datetime.now()
        
        urgency_score = 0
        
        if self.detect_imminent_launch(text):
            urgency_score += 50
            time_info = self.extract_launch_time(text)
            if 'estimated_hours' in time_info:
                if time_info['estimated_hours'] <= 1:
                    urgency_score += 30
                elif time_info['estimated_hours'] <= 3:
                    urgency_score += 20
                elif time_info['estimated_hours'] <= 6:
                    urgency_score += 10
            
            if 'specific_time' in time_info:
                urgency_score += 15
        
        time_diff = datetime.now() - post_time
        if time_diff.total_seconds() <= 3600:
            urgency_score += 25
        elif time_diff.total_seconds() <= 10800:
            urgency_score += 15
        
        return urgency_score
    
    def send_telegram(self, message):
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
        posts = []
        for subreddit in self.all_subreddits:
            try:
                new_posts = await self.reddit_api.get_new_posts(subreddit, limit=10)
                for keyword in random.sample(self.keywords, min(5, len(self.keywords))):
                    keyword_posts = await self.reddit_api.search_posts(subreddit, keyword, limit=5)
                    new_posts.extend(keyword_posts)
                    await asyncio.sleep(1)
                
                for post in new_posts:
                    post_id = f"reddit_{post.get('id', '')}"
                    if post_id in self.vistos:
                        continue
                    
                    self.vistos.add(post_id)
                    text = f"{post['title']} {post['selftext']}".lower()
                    
                    found_keywords = [kw for kw in self.keywords if kw.lower() in text]
                    
                    if found_keywords and post['score'] >= 2:
                        posts.append({
                            **post,
                            'keywords': found_keywords,
                            'relevance_score': len(found_keywords) + (post['score'] / 50) + (post['num_comments'] / 20)
                        })
                        logger.info(f"📝 Reddit: {post['title'][:60]}...")
                
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"❌ Error monitoring r/{subreddit}: {e}")
                continue
        return posts
    
    async def monitor_twitter(self):
        tweets = []
        if not TWITTER_BEARER_TOKEN:
            return tweets
        
        self.twitter_cycle += 1
        if self.twitter_cycle % 2 != 0:
            logger.info("🐦 Twitter: Pulando ciclo para reduzir rate limiting")
            return tweets
        
        try:
            keyword_groups = [
                "presale OR launch OR token OR airdrop",
                "whitelist OR ido OR gem OR moonshot",
                "memecoin OR dogcoin OR catcoin",
                "stealth launch OR fair launch"
            ]
            
            for query in keyword_groups:
                found_tweets = await self.twitter_api.search_tweets(query, limit=8)
                
                for tweet in found_tweets:
                    tweet_id = f"twitter_{tweet.get('id', '')}"
                    if tweet_id in self.vistos:
                        continue
                    
                    self.vistos.add(tweet_id)
                    text = tweet['text'].lower()
                    
                    found_keywords = [kw for kw in self.keywords if kw.lower() in text]
                    
                    if found_keywords and tweet['likes'] >= 3:
                        tweets.append({
                            **tweet,
                            'keywords': found_keywords,
                            'relevance_score': len(found_keywords) + (tweet['likes'] / 100) + (tweet['retweets'] / 50)
                        })
                        logger.info(f"🐦 Twitter: {tweet['text'][:60]}...")
                
                await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"❌ Error monitoring Twitter: {e}")
        return tweets
    
    async def monitor_sources(self):
        try:
            reddit_posts, twitter_tweets = await asyncio.gather(
                self.monitor_reddit(),
                self.monitor_twitter(),
                return_exceptions=True
            )
            
            if isinstance(reddit_posts, Exception):
                logger.error(f"Reddit monitoring failed: {reddit_posts}")
                reddit_posts = []
            if isinstance(twitter_tweets, Exception):
                logger.error(f"Twitter monitoring failed: {twitter_tweets}")
                twitter_tweets = []
            
            all_content = reddit_posts + twitter_tweets
            all_content.sort(key=lambda x: x['relevance_score'], reverse=True)
            
            logger.info(f"📊 Reddit: {len(reddit_posts)}, Twitter: {len(twitter_tweets)}")
            return all_content[:25]
            
        except Exception as e:
            logger.error(f"❌ Error in monitor_sources: {e}")
            return []
    
    async def analyze_content(self, content_list):
        opportunities = []
        token_mentions = {}
        
        for content in content_list:
            text = ""
            if content['source'] == 'reddit':
                text = f"{content['title']} {content['selftext']}"
            else:
                text = content['text']
            
            # Adiciona a análise de sentimento ao conteúdo
            sentiment_analysis = self.sentiment_analyzer.analyze_sentiment(text)
            content['sentiment'] = sentiment_analysis

            urgency_score = self.calculate_urgency_score(content)
            
            if urgency_score < URGENCY_THRESHOLD:
                continue
            
            is_imminent = self.detect_imminent_launch(text)
            
            if is_imminent:
                time_info = self.extract_launch_time(text)
                confidence = 'VERY_HIGH' if urgency_score > 60 else 'HIGH'
                
                opportunities.append({
                    'type': 'IMMINENT_LAUNCH',
                    'title': content.get('title', content.get('text', '')[:100]),
                    'url': content['url'],
                    'source': content['source'],
                    'keywords': content['keywords'],
                    'score': content.get('score', content.get('likes', 0)),
                    'urgency_score': urgency_score,
                    'time_info': time_info,
                    'confidence': confidence,
                    'id': content['id'],
                    'sentiment': content['sentiment'] # Adiciona a análise de sentimento aqui
                })
            
            tokens = self.extract_tokens(text)
            for token in tokens:
                token_mentions[token] = token_mentions.get(token, 0) + 1
        
        for token, count in token_mentions.items():
            if count >= 2:
                opportunities.append({
                    'type': 'TRENDING_TOKEN',
                    'token': token,
                    'mentions': count,
                    'source': 'multiple',
                    'confidence': 'HIGH' if count >= 5 else 'MEDIUM',
                    'id': f"token_{token}"
                })
        
        opportunities.sort(key=lambda x: x.get('urgency_score', 0) if 'urgency_score' in x else 0, reverse=True)
        
        return opportunities
    
    def detect_presale_patterns(self, text):
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
        patterns = [
            r'\$([A-Z]{2,8})\b',
            r'\b([A-Z]{3,8})\b.*(token|coin|launch|presale)',
            r'(buy|get|trade).*\b([A-Z]{3,8})\b'
        ]
        
        tokens = set()
        for pattern in patterns:
            matches = re.findall(pattern, text.upper())
            for match in matches:
                token = match[0] if isinstance(match, tuple) else match
                
                if (token and len(token) >= 2 and 
                    token not in ["ETH", "BTC", "BNB", "USDT", "USDC", "USD", "THE", "AND", "FOR", "YOU"]):
                    tokens.add(token)
        
        return list(tokens)
    
    def create_alpha_message(self, opportunity):
        if opportunity['type'] == 'IMMINENT_LAUNCH':
            source_emoji = "🐦" if opportunity['source'] == 'twitter' else "🌐"
            
            # Análise de Sentimento
            sentiment = opportunity.get('sentiment', {})
            sentiment_score = sentiment.get('score', 0)
            sentiment_magnitude = sentiment.get('magnitude', 0)
            
            sentiment_status = "Positivo" if sentiment_score > 0.2 else ("Negativo" if sentiment_score < -0.2 else "Neutro")
            
            time_info = ""
            if 'time_info' in opportunity and opportunity['time_info']:
                if 'estimated_hours' in opportunity['time_info']:
                    time_info = f"⏰ <b>Lançamento em:</b> {opportunity['time_info']['estimated_hours']} horas\n"
                elif 'estimated_minutes' in opportunity['time_info']:
                    time_info = f"⏰ <b>Lançamento em:</b> {opportunity['time_info']['estimated_minutes']} minutos\n"
                if 'specific_time' in opportunity['time_info']:
                    time_info += f"🕒 <b>Horário específico:</b> {opportunity['time_info']['specific_time']}\n"
            
            message = f"🚨🚨 <b>ALPHA DETECTADO - {opportunity['source'].upper()}</b> 🚨🚨\n\n"
            message += f"{source_emoji} <b>{opportunity['title']}</b>\n"
            message += f"🔗 <a href='{opportunity['url']}'>Ver anúncio original</a>\n"
            message += f"🔥 <b>Nível de Urgência:</b> {opportunity['urgency_score']}/100\n"
            message += f"💬 <b>Sentimento Social:</b> {sentiment_status} (Score: {sentiment_score:.2f}, Mag: {sentiment_magnitude:.2f})\n"
            message += time_info
            message += f"🔍 <b>Keywords:</b> {', '.join(opportunity['keywords'][:3])}\n\n"
            message += "⚡ <b>OPORTUNIDADE DE EARLY ENTRY!</b>\n"
            message += "💡 <i>DYOR (Do Your Own Research) antes de investir!</i>"
            
        elif opportunity['type'] == 'TRENDING_TOKEN':
            message = f"📈 <b>TOKEN TRENDING - MÚLTIPLAS FONTES</b>\n\n"
            message += f"🏷 <b>Token:</b> ${opportunity['token']}\n"
            message += f"🔊 <b>Mentions:</b> {opportunity['mentions']}\n"
            message += f"🌐 <b>Fonte:</b> {opportunity['source']}\n"
            message += f"🎯 <b>Confiança:</b> {opportunity['confidence']}\n\n"
            message += "📢 <b>Está sendo muito falado!</b>\n"
            message += "🔍 <i>Fique de olho, um lançamento pode estar próximo!</i>"
        
        message += f"\n\n⏰ <i>{datetime.now().strftime('%d/%m %H:%M:%S')}</i>"
        return message
    
    async def run(self):
        logger.info("🤖 Alpha Hunter Bot com Reddit + Twitter + Análise de Sentimento iniciado!")
        
        if TELEGRAM_TOKEN and CHAT_ID:
            self.send_telegram("🚀 <b>Alpha Hunter Bot V2 iniciado!</b>\n🔍 Monitorando com Inteligência de Sentimento\n🎯 Dados de múltiplas fontes")
        
        await asyncio.sleep(10)
        
        while True:
            try:
                content = await self.monitor_sources()
                opportunities = await self.analyze_content(content)
                
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
                
                if opportunities:
                    base_wait = 120
                    logger.info(f"🔥 Oportunidades encontradas! Verificando novamente em {base_wait//60} minutos...")
                else:
                    base_wait = CHECK_INTERVAL
                    logger.info(f"⏳ Nenhuma oportunidade. Próxima verificação em {base_wait//60} minutos...")
                
                wait_time = random.randint(base_wait, base_wait + 120)
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"❌ Erro no loop principal: {e}")
                await asyncio.sleep(300)
    
    async def close(self):
        await self.reddit_api.close()
        await self.twitter_api.close()

# Função principal
async def main():
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
        bot_task = asyncio.create_task(bot.run())
        
        while True:
            await asyncio.sleep(3600)
            
    except KeyboardInterrupt:
        logger.info("🤖 Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    import threading
    def run_flask():
        app.run(host='0.0.0.0', port=PORT, debug=False)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    asyncio.run(main())
