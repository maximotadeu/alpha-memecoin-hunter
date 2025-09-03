import os
import requests
import time
import logging
import random
import re
import aiohttp
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Configurações
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

# Fontes de ALPHA com URLs específicas
SOURCES = {
    "reddit": {
        "enabled": True,
        "subreddits": [
            "CryptoMoonShots", "CryptoCurrency", "CryptoMars",
            "CryptoGems", "Crypto_General", "CryptoMoon"
        ],
        "keywords": [
            "presale", "launching", "new project", "meme token",
            "fair launch", "low cap", "hidden gem", "stealth launch",
            "ido", "initial offering", "token sale", "going live"
        ]
    },
    "launchpads": {
        "enabled": True,
        "sites": {
            "pinksale": {
                "url": "https://www.pinksale.finance/launchpad",
                "name": "PinkSale"
            },
            "dxsale": {
                "url": "https://www.dxsale.network/presales", 
                "name": "DxSale"
            },
            "unicrypt": {
                "url": "https://www.unicrypt.network/presales",
                "name": "Unicrypt"
            }
        }
    }
}

class AlphaHunterBot:
    def __init__(self):
        self.vistos = set()
    
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

    async def monitor_reddit(self):
        """Monitora Reddit para novos posts com mais detalhes"""
        posts = []
        try:
            for subreddit in SOURCES["reddit"]["subreddits"]:
                url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=10"
                headers = {"User-Agent": "Mozilla/5.0 (Alpha Hunter Bot)"}
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            for post in data.get("data", {}).get("children", []):
                                post_data = post.get("data", {})
                                title = post_data.get("title", "").lower()
                                content = post_data.get("selftext", "").lower()
                                
                                # Verificar keywords com scoring
                                text = f"{title} {content}"
                                keyword_matches = []
                                
                                for keyword in SOURCES["reddit"]["keywords"]:
                                    if keyword in text:
                                        keyword_matches.append(keyword)
                                
                                if keyword_matches:
                                    posts.append({
                                        "title": post_data.get("title"),
                                        "url": f"https://reddit.com{post_data.get('permalink')}",
                                        "created": post_data.get("created_utc"),
                                        "subreddit": subreddit,
                                        "keywords": keyword_matches,
                                        "score": len(keyword_matches)
                                    })
                                    
                                    logging.info(f"📝 Reddit encontrado: {post_data.get('title')[:50]}...")
        except Exception as e:
            logging.error(f"Reddit monitor error: {e}")
        
        return posts

    async def monitor_launchpads(self):
        """Monitora sites de launchpad com parsing específico"""
        launches = []
        try:
            for platform, config in SOURCES["launchpads"]["sites"].items():
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(config["url"], timeout=20) as response:
                            if response.status == 200:
                                html = await response.text()
                                soup = BeautifulSoup(html, 'html.parser')
                                
                                # Título da página
                                page_title = soup.title.string if soup.title else "No title"
                                
                                # Procurar por textos específicos
                                launch_texts = []
                                
                                # Diferentes estratégias por platform
                                if platform == "pinksale":
                                    # PinkSale específico
                                    elements = soup.find_all(string=re.compile(r'live|ongoing|upcoming|presale', re.IGNORECASE))
                                    for element in elements:
                                        if len(element.strip()) > 20:  # Textos significativos
                                            launch_texts.append(element.strip())
                                
                                elif platform == "dxsale":
                                    # DxSale específico
                                    elements = soup.find_all(string=re.compile(r'active|live|presale', re.IGNORECASE))
                                    for element in elements:
                                        if len(element.strip()) > 15:
                                            launch_texts.append(element.strip())
                                
                                else:
                                    # Unicrypt e outros
                                    elements = soup.find_all(string=re.compile(r'presale|launch', re.IGNORECASE))
                                    for element in elements:
                                        if len(element.strip()) > 10:
                                            launch_texts.append(element.strip())
                                
                                if launch_texts:
                                    launches.append({
                                        "platform": config["name"],
                                        "url": config["url"],
                                        "title": page_title,
                                        "activity": launch_texts[:3],  # Primeiros 3 textos
                                        "found_at": datetime.now().isoformat()
                                    })
                                    
                                    logging.info(f"🏗️ {config['name']} activity detected")
                                
                except Exception as e:
                    logging.error(f"Error checking {platform}: {e}")
                    continue
                    
        except Exception as e:
            logging.error(f"Launchpad monitor error: {e}")
        
        return launches

    def detect_presale_patterns(self, text):
        """Detecta padrões de presale em textos"""
        patterns = [
            r"presale.*(live|ongoing|active)",
            r"launch.*(tomorrow|today|soon)", 
            r"fair.*launch",
            r"stealth.*launch",
            r"token.*sale.*start",
            r"ido.*(start|begin)",
            r"initial.*offering",
            r"going.*live.*[0-9]",
            r"whitelist.*open"
        ]
        
        for pattern in patterns:
            if re.search(pattern, text.lower()):
                return True
        return False

    def analyze_trends(self, posts):
        """Analisa tendências nos posts"""
        trends = {}
        
        for post in posts:
            text = f"{post.get('title', '')}".lower()
            
            # Padrões para detectar tokens
            patterns = [
                r'\$([A-Z]{3,6})\b',  # $TOKEN
                r'\b([A-Z]{3,6})\b.*(launch|presale|token|coin)',
                r'(buy|get|trade).*\b([A-Z]{3,6})\b',
                r'\b([A-Z]{3,6}).*(airdrop|whitelist|reward)'
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text.upper())
                for match in matches:
                    token = match[0] if isinstance(match, tuple) else match
                    # Filtrar palavras comuns
                    common_words = ["ETH", "BTC", "BNB", "USDT", "USDC", "USD", "THE", "AND", "FOR", "YOU", "ARE"]
                    if token not in common_words and len(token) >= 3:
                        trends[token] = trends.get(token, 0) + 1
        
        return trends

    def create_alpha_message(self, opportunity):
        """Cria mensagem de alpha detalhada"""
        if opportunity["type"] == "PRESALE_ALERT":
            message = f"🚀 <b>PRESALE ALERT - REDDIT</b>\n\n"
            message += f"📢 <b>{opportunity['title']}</b>\n"
            message += f"🌐 <b>Subreddit:</b> r/{opportunity['subreddit']}\n"
            message += f"🔍 <b>Keywords:</b> {', '.join(opportunity['keywords'][:3])}\n"
            message += f"🔗 <a href='{opportunity['url']}'>Ver post</a>\n\n"
            message += "🎯 <b>OPORTUNIDADE DE ALPHA!</b>\n"
            message += "⚠️ <i>Pesquise antes de investir!</i>"
            
        elif opportunity["type"] == "TRENDING_TOKEN":
            message = f"📈 <b>TRENDING TOKEN - REDDIT</b>\n\n"
            message += f"🏷 <b>Token:</b> {opportunity['token']}\n"
            message += f"🔊 <b>Mentions:</b> {opportunity['mentions']}\n"
            message += f"🌐 <b>Fonte:</b> r/{opportunity['source']}\n\n"
            message += "📢 <b>Está sendo muito comentado!</b>\n"
            message += "🔍 <i>Verifique se já listou!</i>"
            
        elif opportunity["type"] == "LAUNCHPAD_ACTIVITY":
            message = f"🏗️ <b>LAUNCHPAD ACTIVITY</b>\n\n"
            message += f"🌐 <b>Platform:</b> {opportunity['platform']}\n"
            message += f"📝 <b>Detectado:</b> {opportunity['title']}\n"
            
            if opportunity.get('activity'):
                message += f"🔍 <b>Atividade:</b>\n"
                for activity in opportunity['activity'][:2]:
                    message += f"• {activity[:50]}...\n"
            
            message += f"🔗 <a href='{opportunity['url']}'>Acessar launchpad</a>\n\n"
            message += "🚀 <b>Possível novo lançamento!</b>"
        
        message += f"\n\n⏰ <i>{datetime.now().strftime('%d/%m %H:%M:%S')}</i>"
        return message

    async def find_alpha_opportunities(self):
        """Encontra oportunidades de alpha"""
        opportunities = []
        
        try:
            # Monitorar fontes
            reddit_posts = await self.monitor_reddit()
            launchpad_launches = await self.monitor_launchpads()
            
            logging.info(f"📊 Reddit: {len(reddit_posts)} posts relevantes")
            logging.info(f"🏗️ Launchpads: {len(launchpad_launches)} atividades")
            
            # Analisar posts do Reddit
            for post in reddit_posts:
                if self.detect_presale_patterns(post["title"]):
                    opportunities.append({
                        "type": "PRESALE_ALERT",
                        "source": "reddit",
                        "title": post["title"],
                        "url": post["url"],
                        "subreddit": post["subreddit"],
                        "keywords": post["keywords"],
                        "confidence": "HIGH"
                    })
            
            # Analisar tendências do Reddit
            reddit_trends = self.analyze_trends(reddit_posts)
            for token, count in reddit_trends.items():
                if count >= 2:  # Mencionado pelo menos 2 vezes
                    opportunities.append({
                        "type": "TRENDING_TOKEN",
                        "token": token,
                        "mentions": count,
                        "source": "reddit",
                        "confidence": "MEDIUM"
                    })
            
            # Adicionar launchpads
            for launch in launchpad_launches:
                opportunities.append({
                    "type": "LAUNCHPAD_ACTIVITY",
                    "platform": launch["platform"],
                    "url": launch["url"],
                    "title": launch["title"],
                    "activity": launch.get("activity", []),
                    "source": "launchpad",
                    "confidence": "HIGH"
                })
                
        except Exception as e:
            logging.error(f"Alpha finding error: {e}")
        
        return opportunities

    async def run(self):
        """Loop principal do bot"""
        logging.info("🤖 Alpha Hunter Bot iniciado!")
        
        self.send_telegram("🚀 <b>Alpha Hunter iniciado!</b>\n🔍 Monitorando presales e tendências\n🎯 Antecipando pumps de 1000%+")
        
        while True:
            try:
                opportunities = await self.find_alpha_opportunities()
                
                logging.info(f"🎯 Total de oportunidades: {len(opportunities)}")
                
                for opp in opportunities:
                    opp_id = f"{opp['type']}_{opp.get('token', '')}_{opp.get('url', '')}"
                    
                    if opp_id not in self.vistos:
                        self.vistos.add(opp_id)
                        
                        message = self.create_alpha_message(opp)
                        if self.send_telegram(message):
                            logging.info(f"✅ Alpha enviado: {opp['type']}")
                            if opp['type'] == 'TRENDING_TOKEN':
                                logging.info(f"   Token: {opp.get('token')}")
                            else:
                                logging.info(f"   Detalhes: {opp.get('title', 'N/A')[:30]}...")
                
                # Esperar tempo aleatório
                wait_time = random.randint(180, 300)  # 3-5 minutos
                logging.info(f"⏳ Próxima verificação em {wait_time//60} minutos...")
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                logging.error(f"Erro no Alpha Hunter: {e}")
                await asyncio.sleep(60)

# Função principal
async def main():
    """Função principal"""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logging.error("❌ Configure TELEGRAM_TOKEN e CHAT_ID!")
        return
    
    logging.info("🚀 Iniciando Alpha Hunter Bot...")
    
    # Iniciar bot
    alpha_bot = AlphaHunterBot()
    await alpha_bot.run()

if __name__ == "__main__":
    asyncio.run(main())
