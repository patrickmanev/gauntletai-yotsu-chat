import { Bold, Italic, Link2, List, Plus, Send, Smile } from 'lucide-react'
import { useState } from 'react'

interface MessageInputProps {
  placeholder?: string
}

export function MessageInput({ placeholder = "Message #social-media" }: MessageInputProps) {
  const [isFormatting, setIsFormatting] = useState(false)

  return (
    <div className="p-4 border-t border-gray-200">
      <div className="border border-gray-200 rounded-md bg-white">
        {isFormatting && (
          <div className="flex items-center gap-2 p-2 border-b border-gray-200">
            <button className="p-1 hover:bg-gray-100 rounded" aria-label="Bold">
              <Bold className="h-4 w-4 text-gray-500" />
            </button>
            <button className="p-1 hover:bg-gray-100 rounded" aria-label="Italic">
              <Italic className="h-4 w-4 text-gray-500" />
            </button>
            <button className="p-1 hover:bg-gray-100 rounded" aria-label="Link">
              <Link2 className="h-4 w-4 text-gray-500" />
            </button>
            <button className="p-1 hover:bg-gray-100 rounded" aria-label="List">
              <List className="h-4 w-4 text-gray-500" />
            </button>
          </div>
        )}
        
        <div className="p-2">
          <textarea
            placeholder={placeholder}
            className="w-full bg-transparent resize-none focus:outline-none min-h-[24px] max-h-[192px] overflow-y-auto leading-6"
            rows={1}
          />
        </div>

        <div className="flex items-center justify-between px-2 pb-2">
          <div className="flex items-center gap-2">
            <button 
              className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100"
              aria-label="Add attachment"
            >
              <Plus className="h-5 w-5 text-gray-500" />
            </button>
            <button 
              className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100"
              onClick={() => setIsFormatting(!isFormatting)}
              aria-label="Toggle formatting options"
            >
              <Bold className="h-5 w-5 text-gray-500" />
            </button>
            <button 
              className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100"
              aria-label="Add emoji"
            >
              <Smile className="h-5 w-5 text-gray-500" />
            </button>
          </div>
          <button 
            className="w-10 h-10 flex items-center justify-center rounded-lg bg-[#2c0929] hover:bg-[#4d1049] text-white"
            aria-label="Send message"
          >
            <Send className="h-5 w-5 -ml-0.5" />
          </button>
        </div>
      </div>
    </div>
  )
}

