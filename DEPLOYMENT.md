# Deploying Proofreader to Streamlit Cloud

## Prerequisites
1. A GitHub account
2. Your proofreader code in a GitHub repository

## Step 1: Prepare Your Repository

### 1.1 Create a GitHub repository (if you haven't already)
```bash
cd /Users/sam/proofreader

# Initialize git (if not already done)
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: Proofreader app"

# Create a new repository on GitHub (via web interface)
# Then connect your local repo to GitHub:
git remote add origin https://github.com/YOUR_USERNAME/proofreader.git
git branch -M main
git push -u origin main
```

### 1.2 Create a secrets file for Streamlit Cloud
Create a file at `.streamlit/secrets.toml` (this file is already gitignored) with your secrets:

```toml
ANTHROPIC_API_KEY = "your-api-key-here"
PROOFREADER_PASSWORD = "your-password-here"
```

**Note:** This file stays LOCAL - you'll enter these secrets in Streamlit Cloud's web interface.

## Step 2: Deploy to Streamlit Cloud

### 2.1 Go to Streamlit Cloud
1. Visit https://share.streamlit.io/
2. Sign in with your GitHub account
3. Click "New app"

### 2.2 Configure your app
1. **Repository:** Select your proofreader repository
2. **Branch:** main (or master)
3. **Main file path:** app.py
4. Click "Advanced settings..."

### 2.3 Add secrets (IMPORTANT!)
In the Advanced settings, paste your secrets in the "Secrets" section:

```toml
ANTHROPIC_API_KEY = "sk-ant-api03-your-actual-key-here"
PROOFREADER_PASSWORD = "your-chosen-password-here"
```

**Important:**
- Replace `your-actual-key-here` with your real Anthropic API key
- Choose a strong password and share it only with your colleagues
- These secrets are stored securely by Streamlit Cloud and never exposed

### 2.4 Deploy
1. Click "Deploy!"
2. Wait for the app to build (2-5 minutes)
3. Your app will be live at: `https://YOUR_USERNAME-proofreader-app-xxxxx.streamlit.app`

## Step 3: Share with Colleagues

### 3.1 Share the URL and password
1. Copy the app URL from Streamlit Cloud
2. Share it with your colleagues along with the password
3. They'll need to enter the password on first visit

### 3.2 Changing the password
To change the password:
1. Go to Streamlit Cloud dashboard
2. Select your app
3. Go to Settings → Secrets
4. Update `PROOFREADER_PASSWORD`
5. Click "Save"
6. The app will restart automatically

## Step 4: Updating the App

When you make changes to your code:

```bash
# Make your changes
# Then commit and push
git add .
git commit -m "Description of changes"
git push

# Streamlit Cloud will automatically redeploy within 1-2 minutes
```

## Important Notes

### File Size Limits
- Streamlit Cloud has storage limits
- The `references/` folder with PDFs should be included in your repo
- If your master examples or common mistakes PDFs are very large (>100MB), you may need to compress them

### API Key Security
- **NEVER** commit your `.env` file to GitHub
- **NEVER** hardcode API keys in your code
- Always use Streamlit Cloud's secrets management

### Cost Considerations
- Streamlit Cloud free tier: Limited to 1 app, 1GB RAM
- If you need more apps or resources, consider Streamlit Cloud paid tier
- Your Anthropic API costs are separate (billed per API call)

## Troubleshooting

### App won't start
- Check the logs in Streamlit Cloud dashboard
- Verify secrets are correctly formatted (no extra quotes or spaces)
- Ensure all dependencies are in `requirements.txt`

### "Module not found" errors
- Make sure all imports are in `requirements.txt`
- Streamlit Cloud uses Python 3.9+ by default

### Password not working
- Check secrets in Streamlit Cloud dashboard
- Ensure no extra spaces in the password
- Try restarting the app from the dashboard

## Alternative: Local Network Deployment

If you want to host it on your local network instead:

```bash
# Run on your local machine
streamlit run app.py --server.port 8501 --server.address 0.0.0.0

# Share this URL with colleagues on your network:
# http://YOUR_LOCAL_IP:8501
```

To find your local IP:
- Mac: System Preferences → Network → Advanced → TCP/IP
- Or run: `ifconfig | grep "inet " | grep -v 127.0.0.1`
