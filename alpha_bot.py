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

# Fontes de ALPHA
SOURCES = {
    "reddit": {
        "enabled": True,
        "subreddits": [
            "CryptoMoonShots", "CryptoCurrency", "CryptoMars",
            "CryptoGems", "Crypto_General"
        ],
        "keywords": [
            "presale", "launching", "new project", "meme token",
            "fair launch", "low cap", "hidden gem", "stealth launch"
        ]
    },
    "launchpads": {
        "enabled": True,
        "sites": [
            "https://www.pinksale.finance",
            "https://www.dxsale.network", 
            "https://www.unicrypt.network"
        ]
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
        """Monitora Reddit para novos posts"""
        posts = []
        try:
            for subreddit in SOURCES["reddit"]["subreddits"]:
                url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=5"
                headers = {"User-Agent": "Mozilla/5.0"}
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            for post in data.get("data", {}).get("children", []):
                                post_data = post.get("data", {})
                                title = post_data.get("title", "").lower()
                                content = post_data.get("selftext", "").lower()
                                
                                # Verificar keywords
                                text = f"{title} {content}"
                                if any(keyword in text for keyword in SOURCES["reddit"]["keywords"]):
                                    posts.append({
                                        "title": post_data.get("title"),
                                        "url": f"https://reddit.com{post_data.get('permalink')}",
                                        "created": post_data.get("created_utc"),
                                        "subreddit": subreddit
                                    })
        except Exception as e:
            logging.error(f"Reddit monitor error: {e}")
        
        return posts

    async def monitor_launchpads(self):
        """Monitora sites de launchpad"""
        launches = []
        try:
            for site in SOURCES["launchpads"]["sites"]:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(site, timeout=15) as response:
                            if response.status == 200:
                                html = await response.text()
                                soup = BeautifulSoup(html, 'html.parser')
                                
                                # Procurar por textos de lançamento
                                text = soup.get_text().lower()
                                launch_keywords = ["live", "launch", "presale", "ongoing", "upcoming"]
                                
                                if any(keyword in text for keyword in launch_keywords):
                                    launches.append({
                                        "site": site,
                                        "title": soup.title.string if soup.title else site,
                                        "url": site
                                    })
                except Exception as e:
                    logging.error(f"Error checking {site}: {e}")
                    continue
        except Exception as e:
            logging.error(f"Launchpad monitor error: {e}")
        
        return launches

    def detect_presale_patterns(self, text):
        """Detecta padrões de presale em textos"""
        patterns = [
            r"presale.*live",
            r"launch.*tomorrow", 
            r"fair.*launch",
            r"stealth.*launch",
            r"token.*sale",
            r"ido.*starting",
            r"initial.*offering",
            r"going.*live"
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
            
            # Procurar por nomes de tokens (3-5 letras maiúsculas)
            potential_tokens = re.findall(r'\b[A-Z]{3,5}\b', text.upper())
            for token in potential_tokens:
                if token not in ["ETH", "BTC", "BNB", "USDT", "USDC", "USD"]:
                    trends[token] = trends.get(token, 0) + 1
        
        return trends

    def create_alpha_message(self, opportunity):
        """Cria mensagem de alpha"""
        if opportunity["type"] == "PRESALE_ALERT":
            message = f"🚀 <b>PRESALE ALERT - {opportunity['source'].upper()}</b>\n\n"
            message += f"📢 <b>{opportunity['title']}</b>\n"
            message += f"🌐 <b>Fonte:</b> {opportunity.get('subreddit', opportunity['source'])}\n"
            message += f"🔗 <a href='{opportunity['url']}'>Ver detalhes</a>\n\n"
            message += "🎯 <b>OPORTUNIDADE DE ALPHA!</b>\n"
            message += "⚠️ <i>Pesquise antes de investir!</i>"
            
        elif opportunity["type"] == "TRENDING_TOKEN":
            message = f"📈 <b>TRENDING TOKEN</b>\n\n"
            message += f"🏷 <b>Token:</b> {opportunity['token']}\n"
            message += f"🔊 <b>Mentions:</b> {opportunity['mentions']}\n"
            message += f"🌐 <b>Fonte:</b> {opportunity['source']}\n\n"
            message += "📢 <b>Está sendo muito comentado!</b>\n"
            message += "🔍 <i>Verifique se já listou!</i>"
            
        elif opportunity["type"] == "LAUNCHPAD_LAUNCH":
            message = f"🏗️ <b>LAUNCHPAD ACTIVITY</b>\n\n"
            message += f"🌐 <b>Site:</b> {opportunity['site']}\n"
            message += f"📝 <b>Detectado:</b> Nova atividade\n"
            message += f"🔗 <a href='{opportunity['url']}'>Acessar site</a>\n\n"
            message += "🚀 <b>Possível novo lançamento!</b>"
        
        message += f"\n\n⏰ <i>{datetime.now().strftime('%H:%M:%S')}</i>"
        return message

    async def find_alpha_opportunities(self):
        """Encontra oportunidades de alpha"""
        opportunities = []
        
        try:
            # Monitorar fontes
            reddit_posts = await self.monitor_reddit()
            launchpad_launches = await self.monitor_launchpads()
            
            # Analisar posts do Reddit
            for post in reddit_posts:
                if self.detect_presale_patterns(post["title"]):
                    opportunities.append({
                        "type": "PRESALE_ALERT",
                        "source": "reddit",
                        "title": post["title"],
                        "url": post["url"],
                        "subreddit": post["subreddit"],
                        "confidence": "HIGH"
                    })
            
            # Analisar tendências
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
                    "type": "LAUNCHPAD_LAUNCH",
                    "site": launch["site"],
                    "url": launch["url"],
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
                
                for opp in opportunities:
                    opp_id = f"{opp['type']}_{opp.get('token', '')}_{opp.get('url', '')}"
                    
                    if opp_id not in self.vistos:
                        self.vistos.add(opp_id)
                        
                        message = self.create_alpha_message(opp)
                        if self.send_telegram(message):
                            logging.info(f"✅ Alpha encontrado: {opp['type']}")
                            logging.info(f"📝 Detalhes: {opp.get('title', opp.get('token', 'N/A'))}")
                
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
