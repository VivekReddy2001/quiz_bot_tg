# 🎯 Telegram Quiz Bot - Render Deployment

A zero-maintenance Telegram quiz bot optimized for Render's free tier. Create interactive MCQ quizzes instantly!

## ✨ Features

- 🔒 **Anonymous & Non-Anonymous Quizzes**
- 📱 **Interactive Telegram Interface**
- 🚀 **Zero Maintenance** - Runs 24/7 on Render
- 💾 **Smart Memory Management**
- 🔄 **Auto-retry & Error Handling**
- 📊 **Built-in Analytics Dashboard**

## 🚀 Quick Deploy to Render (5 Minutes)

### Step 1: Prepare Your Bot Token

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot` and follow instructions
3. Copy your bot token (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Deploy to Render

1. **Fork/Clone this repository**
2. **Connect to Render:**
   - Go to [render.com](https://render.com)
   - Sign up/Login with GitHub
   - Click "New +" → "Web Service"
   - Connect your GitHub repository

3. **Configure Service:**
   - **Name:** `your-quiz-bot` (choose unique name)
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn --bind 0.0.0.0:$PORT app:app`
   - **Plan:** `Free`

4. **Set Environment Variables:**
   - `TELEGRAM_BOT_TOKEN` = `your_bot_token_here`
   - `WEBHOOK_URL` = `https://your-app-name.onrender.com/your_bot_token_here`

5. **Deploy!** 🚀

### Step 3: Set Webhook

1. Visit: `https://your-app-name.onrender.com/set_webhook`
2. You should see: ✅ Webhook set successfully!

### Step 4: Test Your Bot

1. Message your bot on Telegram
2. Send `/start`
3. Create your first quiz! 🎉

## 📋 Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather | `123456789:ABCdef...` |
| `WEBHOOK_URL` | Your webhook URL | `https://mybot.onrender.com/123456789:ABCdef...` |

## 🛠️ Local Development

```bash
# Clone repository
git clone <your-repo>
cd quiz_bot_tg

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export TELEGRAM_BOT_TOKEN="your_token_here"
export WEBHOOK_URL="https://your-ngrok-url.com/your_token_here"

# Run locally
python app.py
```

## 📊 Bot Commands

- `/start` - Begin quiz creation
- `/help` - Show help message
- `/template` - Get JSON template
- `/status` - Check bot status

## 🎯 Quiz JSON Format

```json
{
  "all_q": [
    {
      "q": "What is the capital of France? 🇫🇷",
      "o": ["London", "Paris", "Berlin", "Madrid"],
      "c": 1,
      "e": "Paris is the capital of France 🗼"
    }
  ]
}
```

- `q` - Question text (max 300 chars)
- `o` - Options array (2-10 options, max 100 chars each)
- `c` - Correct answer index (0=first option, 1=second, etc.)
- `e` - Explanation (optional, max 200 chars)

## 🔧 Management Endpoints

- `/` - Dashboard & status
- `/health` - Health check
- `/set_webhook` - Set webhook URL
- `/webhook_info` - Check webhook status
- `/debug` - Debug information

## 🆘 Troubleshooting

### Bot not responding?
1. Check webhook: `/webhook_info`
2. Reset webhook: `/set_webhook`
3. Check logs in Render dashboard

### Environment variables not working?
1. Go to Render dashboard → Your service → Environment
2. Make sure variables are set correctly
3. Redeploy the service

### Rate limiting issues?
The bot includes automatic retry logic and rate limiting protection.

## 💡 Tips for Success

1. **Keep it simple** - Start with basic quizzes
2. **Test locally first** - Use ngrok for local webhook testing
3. **Monitor logs** - Check Render dashboard for errors
4. **Use the template** - Copy the JSON template and modify it

## 📈 Scaling

Render free tier includes:
- ✅ 750 hours/month (enough for 24/7)
- ✅ Automatic scaling
- ✅ Custom domains
- ✅ SSL certificates

## 🔒 Security

- Environment variables are encrypted
- No sensitive data stored in memory
- Automatic cleanup of old user data
- Request timeout protection

## 🎉 Success!

Your bot is now running 24/7 with zero maintenance required! 

Visit your dashboard at: `https://your-app-name.onrender.com`

---

**Need help?** Check the logs in your Render dashboard or create an issue in this repository.
