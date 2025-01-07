'use client'

import * as React from 'react'
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Bold, Italic, Link, PlusCircle, Smile } from 'lucide-react'

interface ChatInputProps {
  channelName: string
}

export function ChatInput({ channelName }: ChatInputProps) {
  const [message, setMessage] = React.useState('')
  const textareaRef = React.useRef<HTMLTextAreaElement>(null)

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const textarea = e.target
    setMessage(textarea.value)
    
    // Reset height to auto to properly calculate new height
    textarea.style.height = 'auto'
    // Set new height based on scrollHeight
    textarea.style.height = `${textarea.scrollHeight}px`
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      // Handle message send
      console.log('Sending message:', message)
      setMessage('')
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    }
  }

  return (
    <div className="relative">
      <div className="absolute bottom-full mb-2 flex items-center gap-1">
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <Bold className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <Italic className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <Link className="h-4 w-4" />
        </Button>
      </div>
      <div className="relative">
        <Textarea
          ref={textareaRef}
          value={message}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={`Message #${channelName}`}
          className="min-h-[44px] max-h-[300px] pr-20 resize-none"
          rows={1}
        />
        <div className="absolute right-2 bottom-2 flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <PlusCircle className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <Smile className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

