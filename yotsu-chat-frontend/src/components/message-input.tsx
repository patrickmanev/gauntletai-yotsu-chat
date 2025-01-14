import { Plus, Send, Smile } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'

interface MessageInputProps {
  placeholder?: string
}

export function MessageInput({ placeholder = "Message #social-media" }: MessageInputProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const updateHeight = () => {
    const textarea = textareaRef.current
    if (textarea) {
      // Reset height to auto first to properly calculate new height
      textarea.style.height = '24px'
      
      // Only adjust height if there's content
      if (value.length > 0) {
        const newHeight = Math.min(textarea.scrollHeight, 192)
        textarea.style.height = `${newHeight}px`
      }
    }
  }

  // Update height when value changes
  useEffect(() => {
    updateHeight()
  }, [value])

  // Ensure proper initial height
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = '24px'
    }
  }, [])

  return (
    <div className="p-4 border-t border-gray-200">
      <div className="border border-gray-200 rounded-md bg-white">
        <div className="p-2">
          <textarea
            ref={textareaRef}
            placeholder={placeholder}
            value={value}
            onChange={(e) => {
              setValue(e.target.value)
            }}
            className="w-full bg-transparent text-gray-900 resize-none focus:outline-none min-h-[24px] max-h-[192px] overflow-y-auto leading-6"
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

