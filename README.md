# Yotsu Chat

A modern chat application built with FastAPI and Next.js.

## Project Structure

- `app/` - Backend FastAPI application
- `webapp/` - Frontend Next.js application

## Setup

### Backend (FastAPI)

1. Create a virtual environment:
```bash
python -m venv yotsu-chat-venv
source yotsu-chat-venv/bin/activate  # On Windows use: .\yotsu-chat-venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the backend server:
```bash
uvicorn main:app --reload
```

### Frontend (Next.js)

1. Install dependencies:
```bash
cd webapp
npm install
```

2. Run the development server:
```bash
npm run dev
```

## Features

- Real-time chat functionality
- Channel-based communication
- Modern UI with Tailwind CSS
- WebSocket-based message delivery
- User presence tracking 