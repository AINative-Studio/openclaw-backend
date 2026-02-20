# Pre-Event Email: Agent Swarm Live Build Session

**Event Date:** January 28, 2026 at 4:00 PM Pacific Time

---

**Subject:** Get Ready for Tomorrow's Agent Swarm Session - Easy Setup Guide Inside

---

**Hi there!**

We're excited to have you join us tomorrow for the **Agent Swarm Live Build Session** at 4:00 PM Pacific Time.

This email will help you get set up so you can follow along. Don't worry if you've never coded before - we've made this as simple as possible.

---

### What You Need (Choose Your Path)

**Pick the option that fits you best:**

| I am... | What to do |
|---------|------------|
| **Just watching** | Nothing! Just show up with the Luma link |
| **Want to follow along** | Follow the setup steps below (15-20 min) |
| **Already a developer** | Skip to the "Quick Setup" section at the bottom |

---

### Optional: Download Our IDE (Recommended for Beginners)

If you want a nice coding environment with everything in one place, download **AINative Studio IDE** - our own code editor built for this kind of work.

**Download here:** https://github.com/AINative-Studio/AINativeStudio-IDE/releases/tag/v1.1.0

| Your Computer | What to Download |
|---------------|------------------|
| **Windows** | Look for the `.exe` file |
| **Mac** | Look for the `.dmg` file |
| **Linux** | Look for the `.AppImage` or `.deb` file |

**How to install:**
1. Go to the link above
2. Scroll down to "Assets"
3. Click on the file that matches your computer
4. Run the installer like any other app

This is optional - you can also use Terminal/Command Prompt, VS Code, or any editor you like.

---

### Step 1: Get Python on Your Computer

Python is the programming language we'll use. Think of it like installing an app.

**On Mac:**
1. Open the app called "Terminal" (press Cmd + Space, type "Terminal", hit Enter)
2. Copy and paste this line, then press Enter:
   ```
   brew install python
   ```
3. If that doesn't work, go to https://www.python.org/downloads/ and click the big yellow "Download" button, then run the installer

**On Windows:**
1. Go to https://www.python.org/downloads/
2. Click the big yellow "Download Python" button
3. Run the installer
4. **IMPORTANT:** Check the box that says "Add Python to PATH" before clicking Install

**To check if it worked:**
Open Terminal (Mac) or Command Prompt (Windows) and type:
```
python --version
```
You should see something like "Python 3.11.x" - any version 3.10 or higher is fine.

---

### Step 2: Install the Tools We'll Use

Copy and paste this line into your Terminal/Command Prompt and press Enter:

```
pip install ainative anthropic google-generativeai httpx
```

You'll see some text scroll by. Wait until it stops and you see your cursor again.

---

### Step 3: Get Your API Keys

You'll need two "keys" - think of them like passwords that let your code talk to AI services.

**AINative API Key (Required):**
1. Go to https://ainative.studio
2. Sign up or log in
3. Go to **Developer Settings → API Keys**
4. Click "Create New Key"
5. Copy the key (it looks like a long random string)
6. Save it somewhere safe (like a notes app)

**Choose Your AI Provider (Pick ONE):**

| Option | Best for |
|--------|----------|
| **Claude (Anthropic)** | Most popular, what we'll demo with |
| **Gemini (Google)** | Great free tier, good alternative |

**Option A - Anthropic API Key (for Claude):**
1. Go to https://console.anthropic.com
2. Sign up or log in
3. Go to API Keys
4. Click "Create Key"
5. Copy and save it

**Option B - Google API Key (for Gemini):**
1. Go to https://aistudio.google.com/apikey
2. Sign up or log in with your Google account
3. Click "Create API Key"
4. Copy and save it

---

### Step 4: Set Up Your Keys

**On Mac/Linux:**
Open Terminal and paste these lines (replace the "xxx" parts with your actual keys):

```
export AINATIVE_API_KEY="your_ainative_key_here"
```

Then add ONE of these depending on which AI you chose:

```
# If using Claude:
export ANTHROPIC_API_KEY="your_anthropic_key_here"

# If using Gemini:
export GOOGLE_API_KEY="your_google_key_here"
```

**On Windows (Command Prompt):**
```
set AINATIVE_API_KEY=your_ainative_key_here
```

Then add ONE of these:
```
# If using Claude:
set ANTHROPIC_API_KEY=your_anthropic_key_here

# If using Gemini:
set GOOGLE_API_KEY=your_google_key_here
```

---

### Step 5: Test That Everything Works

Copy and paste this into your Terminal/Command Prompt:

**If using Claude:**
```
python -c "import ainative, anthropic; print('You are all set!')"
```

**If using Gemini:**
```
python -c "import ainative, google.generativeai; print('You are all set!')"
```

If you see **"You are all set!"** - congratulations, you're ready for tomorrow!

---

### What If Something Goes Wrong?

| Problem | Solution |
|---------|----------|
| "python not found" | Try `python3` instead of `python` |
| "pip not found" | Try `pip3` instead of `pip` |
| "Permission denied" | Add `sudo` before the command (Mac) or run as Administrator (Windows) |
| "Module not found" | Run the pip install command from Step 2 again |
| Still stuck | Reply to this email or DM us - we'll help! |

---

### Quick Setup (For Experienced Developers)

```bash
# Optional: Download AINative Studio IDE
# https://github.com/AINative-Studio/AINativeStudio-IDE/releases/tag/v1.1.0

# Install packages
pip install ainative anthropic google-generativeai httpx

# Set AINative key (required)
export AINATIVE_API_KEY="your_key"

# Set ONE of these (your choice)
export ANTHROPIC_API_KEY="your_key"    # For Claude
export GOOGLE_API_KEY="your_key"        # For Gemini

# Test
python -c "import ainative; print('Ready')"
```

---

### Don't Want to Code? That's Okay!

If this feels overwhelming, you can absolutely just **watch and learn**. You'll still understand:
- How multi-agent AI systems work
- What ZeroDB does for agent memory
- How autonomous workflows run
- When this technology might help your projects

No coding required to get value from the session.

---

### Event Details

- **When:** Tomorrow, January 28, 2026 at 4:00 PM Pacific Time
- **Where:** Online (use your Luma registration link)
- **Duration:** 1 hour
- **Cost:** Free

---

### Questions?

Just reply to this email. We're here to help!

See you tomorrow,

**The AINative Team**
Toby, Karsten & Ranveer

---

P.S. - If you get stuck during setup, show up 10 minutes early tomorrow. We'll have time at the start to help troubleshoot.
