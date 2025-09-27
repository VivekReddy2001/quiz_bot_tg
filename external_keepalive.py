#!/usr/bin/env python3
"""
External Keep-Alive Service for Quiz Bot
Run this on a different free service to keep your main bot awake
"""
import requests
import time
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Your bot URL (change this to your actual Render URL)
BOT_URL = "https://your-quiz-bot.onrender.com"

def ping_bot():
    """Ping the bot to keep it awake"""
    try:
        response = requests.get(f"{BOT_URL}/health", timeout=30)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Bot pinged successfully - Uptime: {data.get('uptime_seconds', 0)}s")
            return True
        else:
            logger.warning(f"❌ Bot ping failed: {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        logger.warning("⏰ Bot ping timeout")
        return False
    except Exception as e:
        logger.error(f"❌ Bot ping error: {e}")
        return False

def main():
    """Main keep-alive loop"""
    logger.info("🚀 External Keep-Alive Service Starting...")
    logger.info(f"Target Bot: {BOT_URL}")
    
    ping_count = 0
    success_count = 0
    
    while True:
        try:
            ping_count += 1
            logger.info(f"📡 Ping #{ping_count} at {datetime.now().strftime('%H:%M:%S')}")
            
            if ping_bot():
                success_count += 1
            
            success_rate = (success_count / ping_count) * 100
            logger.info(f"📊 Success Rate: {success_rate:.1f}% ({success_count}/{ping_count})")
            
            # Wait 13 minutes (780 seconds) - just under Render's 15-minute limit
            logger.info("😴 Sleeping for 13 minutes...")
            time.sleep(780)
            
        except KeyboardInterrupt:
            logger.info("🛑 Keep-alive service stopped by user")
            break
        except Exception as e:
            logger.error(f"❌ Keep-alive error: {e}")
            time.sleep(60)  # Wait 1 minute before retrying

if __name__ == "__main__":
    main()
