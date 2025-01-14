import { X } from 'lucide-react'
import { MessageInput } from './message-input'
import { Message } from './message'

interface ThreadPanelProps {
  threadId: string | null
  onClose: () => void
}

export function ThreadPanel({ threadId, onClose }: ThreadPanelProps) {
  return (
    <div className="w-[400px] border-l border-gray-200 flex flex-col bg-white">
      <div className="h-[48px] p-3 border-b border-gray-200 flex justify-between items-center">
        <h2 className="font-semibold text-gray-900">Thread</h2>
        <button 
          onClick={onClose} 
          className="p-2 rounded-md text-gray-500 hover:bg-gray-200 transition-colors"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
      
      <div className="flex-1 overflow-auto">
        {/* Main message doesn't need thread selection */}
        <Message 
          user={{
            name: "Kenny Park",
            avatar: "/placeholder.svg",
            initials: "KP"
          }}
          timestamp="11:55"
          content="Really need to give some kudos to @Emily for helping out with the new influx of tweets yesterday. People are really really excited about yesterday's announcement."
          onProfileClick={() => {}}
          isInThread={true}
        />

        <div className="relative px-4">
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium text-gray-500">2 Replies</span>
            <div className="flex-1 h-px bg-gray-200 mr-[5%]"></div>
          </div>
        </div>
          
        {/* Replies don't need thread selection */}
        <Message 
          user={{
            name: "Paul Leung",
            avatar: "/placeholder.svg",
            initials: "PL"
          }}
          timestamp="11:56"
          content="No! It was my pleasure! Great to see the enthusiasm out there."
          onProfileClick={() => {}}
          isInThread={true}
        />

        <Message 
          user={{
            name: "Emily Anderson",
            avatar: "/placeholder.svg",
            initials: "EA"
          }}
          timestamp="11:57"
          content="Thanks everyone! Let's keep this momentum going! 🚀"
          onProfileClick={() => {}}
          isInThread={true}
        />
      </div>

      <MessageInput placeholder="Reply in thread" />
    </div>
  )
}

