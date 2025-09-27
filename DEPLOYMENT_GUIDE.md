# 🚀 Complete Render Deployment Guide

## Prerequisites ✅

- GitHub account
- Telegram bot token from [@BotFather](https://t.me/botfather)
- 5 minutes of your time

## Step-by-Step Deployment

### 1. Create Telegram Bot 🤖

1. Open Telegram and message [@BotFather](https://t.me/botfather)
2. Send `/newbot`
3. Choose a name: `My Quiz Bot`
4. Choose a username: `myquizbot123_bot` (must end with `_bot`)
5. **COPY YOUR TOKEN** - looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

### 2. Prepare Your Code 📁

Option A: **Use this repository directly**
```bash
git clone https://github.com/yourusername/quiz_bot_tg.git
cd quiz_bot_tg
```

Option B: **Create new repository**
1. Create new repo on GitHub
2. Upload all files from this project
3. Make sure these files are included:
   - `app.py`
   - `requirements.txt`
   - `render.yaml`
   - `Procfile`

### 3. Deploy to Render 🌐

1. **Go to Render**
   - Visit [render.com](https://render.com)
   - Click "Get Started for Free"
   - Sign up with GitHub

2. **Create Web Service**
   - Click "New +" button
   - Select "Web Service"
   - Choose "Build and deploy from a Git repository"
   - Click "Next"

3. **Connect Repository**
   - Select your repository
   - Click "Connect"

4. **Configure Service**
   ```
   Name: quiz-bot-yourname (choose unique name)
   Environment: Python 3
   Region: Choose closest to you
   Branch: main
   Build Command: pip install -r requirements.txt
   Start Command: gunicorn --bind 0.0.0.0:$PORT app:app
   Plan: Free
   ```

5. **Set Environment Variables**
   - Scroll down to "Environment Variables"
   - Add these variables:
   
   | Key | Value |
   |-----|-------|
   | `TELEGRAM_BOT_TOKEN` | Your bot token from step 1 |
   | `WEBHOOK_URL` | `https://your-service-name.onrender.com/YOUR_BOT_TOKEN` |
   
   **Example:**
   - Service name: `quiz-bot-john`
   - Bot token: `123456789:ABCdef`
   - Webhook URL: `https://quiz-bot-john.onrender.com/123456789:ABCdef`

6. **Deploy**
   - Click "Create Web Service"
   - Wait 2-3 minutes for deployment
   - You'll see "Your service is live" when ready

### 4. Set Webhook 🔗

1. **Get Your Service URL**
   - Copy your service URL: `https://your-service-name.onrender.com`

2. **Set Webhook**
   - Visit: `https://your-service-name.onrender.com/set_webhook`
   - You should see: ✅ Webhook set successfully!

3. **Verify Webhook**
   - Visit: `https://your-service-name.onrender.com/webhook_info`
   - Check that URL is set correctly

### 5. Test Your Bot 🧪

1. **Find your bot on Telegram**
   - Search for your bot username
   - Start a chat

2. **Test commands**
   ```
   /start
   /help
   /template
   /status
   ```

3. **Create a quiz**
   - Send `/start`
   - Choose quiz type
   - Copy the JSON template
   - Customize it with your questions
   - Send it back to the bot

## 🎯 Sample Quiz JSON

```json
{
  "all_q": [
    {
      "q": "What is 2+2? 🔢",
      "o": ["3", "4", "5", "6"],
      "c": 1,
      "e": "Basic math: 2+2=4 ✅"
    },
    {
      "q": "Capital of France? 🇫🇷",
      "o": ["London", "Paris", "Berlin", "Madrid"],
      "c": 1,
      "e": "Paris is the capital of France 🗼"
    }
  ]
}
```

## 🔧 Monitoring & Management

### Dashboard Access
- Visit: `https://your-service-name.onrender.com`
- View statistics, uptime, and bot status

### Useful Endpoints
- `/` - Main dashboard
- `/health` - Health check
- `/set_webhook` - Reset webhook
- `/webhook_info` - Check webhook status
- `/debug` - Debug information

### Render Dashboard
- Go to [dashboard.render.com](https://dashboard.render.com)
- View logs, metrics, and manage your service
- Check for any errors or issues

## 🆘 Troubleshooting

### Bot not responding?
1. **Check webhook status**
   - Visit: `/webhook_info`
   - Make sure URL is correct

2. **Reset webhook**
   - Visit: `/set_webhook`
   - Should show success message

3. **Check logs**
   - Go to Render dashboard
   - Click on your service
   - Check "Logs" tab for errors

### Environment variables not working?
1. **Check variables in Render**
   - Go to your service in Render dashboard
   - Click "Environment" tab
   - Verify both variables are set correctly

2. **Redeploy service**
   - In Render dashboard, click "Manual Deploy"
   - Wait for deployment to complete

### Service keeps sleeping?
- Render free tier sleeps after 15 minutes of inactivity
- It will wake up automatically when someone uses the bot
- This is normal behavior for free tier

### Rate limiting errors?
- The bot has built-in retry logic
- Telegram allows ~30 messages per second
- Bot automatically handles rate limits

## ✅ Success Checklist

- [ ] Bot token obtained from BotFather
- [ ] Repository connected to Render
- [ ] Environment variables set correctly
- [ ] Service deployed successfully
- [ ] Webhook set and verified
- [ ] Bot responds to `/start` command
- [ ] Quiz creation works end-to-end

## 🎉 You're Done!

Your bot is now running 24/7 on Render's free tier with zero maintenance required!

**Your bot URL:** `https://your-service-name.onrender.com`
**Bot username:** `@your_bot_username`

## 💡 Pro Tips

1. **Bookmark your dashboard** - Easy access to bot status
2. **Test regularly** - Send `/status` to check bot health
3. **Monitor logs** - Check Render dashboard occasionally
4. **Keep token secure** - Never share your bot token
5. **Use templates** - Start with provided JSON format

## 🔄 Updates & Maintenance

**Zero maintenance required!** 🎉

- Render automatically handles server updates
- Bot includes automatic error recovery
- Memory management prevents crashes
- No manual intervention needed

**To update bot code:**
1. Push changes to your GitHub repository
2. Render will automatically redeploy
3. No downtime required!

---

**Need more help?** Check the main README or create an issue in the repository.
