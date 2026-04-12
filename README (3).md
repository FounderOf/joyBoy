# 🤖 JoyCannot Discord Bot

> A professional, production-ready multi-purpose Discord bot built with `discord.py 2.x`.

---

## ✨ Features

| System | Description |
|--------|-------------|
| 🛡️ Moderation | kick, ban, timeout, warn, addrole, removerole, move, userinfo, avatar, addemoji, ping, help |
| 🎫 Ticket System | Panel + button, per-guild config, whitelist roles, auto naming |
| 📅 Event Announcements | Slash command, WIB timezone, duration support, auto @everyone + 5-min reminder |
| 📢 Maintenance Broadcast | Owner-only prefix command, sends embed+button to ALL guilds |
| 🌐 Language System | 8 languages: EN, ID, DE, AR, TH, VI, JA, KO |
| 💎 Premium System | Packages, payment methods (QRIS/Bank/E-wallet), DM order notification |
| 👋 Welcome System | Auto embed on guild join with channel picker |
| 🚫 Anti Cross-Channel Spam | Detects same message across 3+ channels → instant ban |

---

## 🛠️ Setup

### 1. Prerequisites

- Python `3.11+`
- A Discord bot application ([Discord Developer Portal](https://discord.com/developers/applications))

### 2. Clone the repo

```bash
git clone https://github.com/yourname/joycannot-bot.git
cd joycannot-bot
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the root directory:

```env
DISCORD_TOKEN=your_bot_token_here
OWNER_ID=your_discord_user_id_here
```

Or set these as Railway environment variables (see Railway Deploy section).

### 5. Required Bot Permissions

Enable these in the Discord Developer Portal under **Bot → Privileged Gateway Intents**:

- ✅ **Server Members Intent**
- ✅ **Message Content Intent**

Invite URL scopes:
- `bot`
- `applications.commands`

Recommended permission integer: `8` (Administrator) — or use fine-grained permissions:  
`Kick Members`, `Ban Members`, `Moderate Members`, `Manage Roles`, `Manage Channels`, `Manage Emojis`, `Move Members`

### 6. Run locally

```bash
python bot.py
```

---

## 🚀 Deploy on Railway

1. **Push to GitHub** — make sure all files are committed.

2. **Create a new Railway project**  
   Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub Repo

3. **Connect your repository**

4. **Set Environment Variables** in Railway Dashboard → Variables:

   | Key | Value |
   |-----|-------|
   | `DISCORD_TOKEN` | Your bot token |
   | `OWNER_ID` | Your Discord user ID |

5. **Verify the Procfile** is present:
   ```
   worker: python bot.py
   ```

6. Railway will auto-detect `requirements.txt` and install dependencies.

7. **Deploy** — Railway will start the bot automatically.

> ⚠️ Make sure to use **Worker** type (not Web). Railway runs the `worker` Procfile entry.

---

## 📁 Project Structure

```
joycannot-bot/
├── bot.py              # Main bot file (all systems included)
├── requirements.txt    # Python dependencies
├── Procfile            # Railway process definition
├── README.md           # This file
├── qris.png            # QRIS payment image (replace with yours)
└── data/
    └── config.json     # Auto-generated guild configuration storage
```

---

## 📖 Command Reference

### Slash Commands (`/`)

#### Moderation
| Command | Description | Permission |
|---------|-------------|------------|
| `/kick @member [reason]` | Kick a member | Kick Members |
| `/ban @member [reason]` | Ban a member | Ban Members |
| `/timeout @member <minutes> [reason]` | Timeout a member | Moderate Members |
| `/warn @member [reason]` | Warn a member | Manage Messages |
| `/addrole @member @role` | Add a role | Manage Roles |
| `/removerole @member @role` | Remove a role | Manage Roles |
| `/move @member #channel` | Move to voice channel | Move Members |
| `/userinfo [@member]` | Show user info | Everyone |
| `/avatar [@member]` | Show user avatar | Everyone |
| `/addemoji <name> <url>` | Add emoji from URL | Manage Emojis |
| `/ping` | Show bot latency | Everyone |
| `/help` | Show command list | Everyone |

#### Tickets
| Command | Description | Permission |
|---------|-------------|------------|
| `/ticket setup` | Configure ticket system | Manage Guild |
| `/ticket panel` | Send ticket panel embed | Manage Guild |
| `/ticket close` | Close current ticket | Manage Channels / Ticket Owner |

#### Events
| Command | Description | Permission |
|---------|-------------|------------|
| `/event create` | Create and announce event | Manage Guild |
| `/event channel #channel` | Set announce channel | Manage Guild |

#### Language
| Command | Description | Permission |
|---------|-------------|------------|
| `/language set <code>` | Set language | Manage Guild |
| `/language list` | List all languages | Everyone |

#### Premium
| Command | Description | Permission |
|---------|-------------|------------|
| `/premium info` | View premium packages | Everyone |
| `/premium order <package> <payment>` | Order a package | Everyone |

---

### Prefix Commands (`!Joy `) — Owner Only

| Command | Description |
|---------|-------------|
| `!Joy maintenance <title> \| <desc> \| <btn_label> \| <btn_url>` | Broadcast maintenance to all servers |
| `!Joy premium list` | List all premium packages |
| `!Joy premium add <n> \| <dur> \| <type> \| <price>` | Add a premium package |
| `!Joy premium remove <name>` | Remove a premium package |
| `!Joy premium payment <qris\|bank\|ewallet> <on\|off>` | Toggle payment methods |
| `!Joy setchannel <guild_id> <channel_id>` | Set main channel for a guild |

---

## 🌐 Supported Languages

| Code | Language |
|------|----------|
| `en` | English (default) |
| `id` | Indonesian |
| `de` | German |
| `ar` | Arabic |
| `th` | Thai |
| `vi` | Vietnamese |
| `ja` | Japanese |
| `ko` | Korean |

---

## 🔒 Anti Cross-Channel Spam

The bot monitors messages in real-time. If the **same message content** is detected in **3 or more different channels** within **8 seconds** by the same user, the bot will:

1. Instantly **ban** the user
2. Log the action to the configured ticket log channel

This only triggers on **identical cross-channel spam**, not normal fast typing.

---

## 📄 License

MIT — Free to use, modify, and distribute.

---

## 🙏 Credits

Built with [discord.py](https://discordpy.readthedocs.io/) · Deployed on [Railway](https://railway.app)
