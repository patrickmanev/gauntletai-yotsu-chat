'use client'

import { MessageSquare, Home, Bell, ChevronDown, Users, Headphones, Settings } from 'lucide-react'
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { ChatInput } from './chat-input'
import { ChannelList } from './channel-list'
import * as React from 'react'

interface Channel {
  channel_id: number
  name: string
  type: string
  created_at: string
}

interface Message {
  message_id: number
  channel_id: number
  user_id: number
  content: string
  created_at: string
  edited_at: string | null
  display_name: string
  parent_id: number | null
  attachments: any[]
}

export function YotsuInterface() {
  const [mounted, setMounted] = React.useState(false)
  const [currentChannel, setCurrentChannel] = React.useState<Channel | null>(null)
  const [messages, setMessages] = React.useState<Message[]>([])
  const [isLoadingMessages, setIsLoadingMessages] = React.useState(false)
  const [hasMoreMessages, setHasMoreMessages] = React.useState(true)
  const scrollAreaRef = React.useRef<HTMLDivElement>(null)
  const lastMessageRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  const handleChannelSelect = async (channel: Channel) => {
    setCurrentChannel(channel)
    setMessages([])
    setHasMoreMessages(true)
    await fetchMessages(channel.channel_id)
  }

  const fetchMessages = async (channelId: number, beforeMessageId?: number) => {
    if (isLoadingMessages || !hasMoreMessages) return

    setIsLoadingMessages(true)
    try {
      const limit = 20
      const url = `/api/messages/channels/${channelId}${beforeMessageId ? `?before=${beforeMessageId}&limit=${limit}` : `?limit=${limit}`}`
      const response = await fetch(url)
      if (!response.ok) throw new Error('Failed to fetch messages')
      
      const newMessages = await response.json()
      setMessages(prev => {
        const combined = beforeMessageId 
          ? [...prev, ...newMessages]
          : newMessages
        return combined.sort((a: Message, b: Message) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
      })
      setHasMoreMessages(newMessages.length === limit)
    } catch (error) {
      console.error('Error fetching messages:', error)
    } finally {
      setIsLoadingMessages(false)
    }
  }

  const handleScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const target = event.target as HTMLDivElement
    const scrollTop = target.scrollTop
    const scrollHeight = target.scrollHeight
    const clientHeight = target.clientHeight

    // Load more messages when scrolled near the top (20px threshold)
    if (scrollTop < 20 && !isLoadingMessages && hasMoreMessages && messages.length > 0) {
      fetchMessages(currentChannel!.channel_id, messages[0].message_id)
    }
  }

  // Scroll to bottom on initial load and when new messages arrive
  React.useEffect(() => {
    if (lastMessageRef.current) {
      lastMessageRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  if (!mounted) {
    return null
  }

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <div className="w-64 flex flex-col bg-[#2C001E] text-white">
        {/* Workspace Header */}
        <div className="p-4 border-b border-white/10">
          <Button variant="ghost" className="w-full justify-between text-white hover:bg-white/10">
            <span className="font-semibold">Acme Inc</span>
            <ChevronDown className="h-4 w-4" />
          </Button>
        </div>

        {/* Navigation */}
        <ScrollArea className="flex-1">
          <div className="p-2 space-y-2">
            <Button variant="ghost" className="w-full justify-start text-white hover:bg-white/10">
              <Home className="mr-2 h-4 w-4" />
              Home
            </Button>
            <Button variant="ghost" className="w-full justify-start text-white hover:bg-white/10">
              <MessageSquare className="mr-2 h-4 w-4" />
              DMs
            </Button>
            <Button variant="ghost" className="w-full justify-start text-white hover:bg-white/10">
              <Bell className="mr-2 h-4 w-4" />
              Activity
            </Button>
          </div>

          <div className="px-3 py-2">
            <h2 className="text-white/70 text-sm font-semibold mb-2">Channels</h2>
            <ChannelList onChannelSelect={handleChannelSelect} />
          </div>
        </ScrollArea>

        {/* User Profile */}
        <div className="p-4 border-t border-white/10">
          <div className="flex items-center gap-2">
            <Avatar className="h-8 w-8">
              <AvatarImage src="/placeholder.svg" />
              <AvatarFallback>U</AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">User Name</p>
              <p className="text-xs text-white/70 truncate">@username</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Channel Header */}
        <header className="h-14 border-b flex items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold"># {currentChannel?.name || 'general'}</h1>
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon">
              <Users className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon">
              <Headphones className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon">
              <Settings className="h-4 w-4" />
            </Button>
          </div>
        </header>

        {/* Messages Area */}
        <ScrollArea className="flex-1 p-4" onScroll={handleScroll} ref={scrollAreaRef}>
          <div className="space-y-4">
            {isLoadingMessages && messages.length === 0 && (
              <div className="text-center text-muted-foreground">Loading messages...</div>
            )}
            {messages.map((message, index) => (
              <div 
                key={message.message_id} 
                className="flex items-start gap-3"
                ref={index === messages.length - 1 ? lastMessageRef : null}
              >
                <Avatar>
                  <AvatarImage src="/placeholder.svg" />
                  <AvatarFallback>{message.display_name[0]}</AvatarFallback>
                </Avatar>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{message.display_name}</span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(message.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-sm">{message.content}</p>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>

        {/* Message Input */}
        <div className="p-4 border-t">
          <ChatInput channelName={currentChannel?.name || 'general'} />
        </div>
      </div>
    </div>
  )
}