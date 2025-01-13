# Yotsu Chat

A modern chat app built with FastAPI and Next.js. Think Slack, but cooler 😎

## Getting Started

### Backend Setup

1. Fire up your virtual environment:
```bash
python -m venv yotsu-chat-venv
# On Windows:
.\yotsu-chat-venv\Scripts\activate
# On Unix/MacOS:
source yotsu-chat-venv/bin/activate
```

2. Install the goods:
```bash
pip install -r requirements.txt
```

3. Start the backend:
```bash
uvicorn main:app --reload
```

### Frontend Setup

1. Head over to the frontend directory and install dependencies:
```bash
cd yotsu-chat-frontend
npm install
```

2. Launch it:
```bash
npm run dev
```

## Cool Features

- Real-time messaging with WebSocket magic ⚡
- Public and private channels 🔒
- Direct messaging 💬
- Thread support for organized convos 🧵
- Emoji reactions because why not 🎉
- User presence tracking 👀
- File sharing capabilities (coming soon) 📎
- Versatile search and filtering (coming soon) 🔍
- Modern UI powered by Tailwind and shadcn/ui 💅

## Tech Stack

- **Backend**: FastAPI + SQLite
- **Frontend**: Next.js 15 + React 18
- **Styling**: Tailwind CSS + shadcn/ui
- **Real-time**: WebSocket
- **Auth**: JWT + 2FA 