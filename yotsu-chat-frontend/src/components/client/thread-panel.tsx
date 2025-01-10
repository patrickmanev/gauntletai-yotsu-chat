import { X } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/client/avatar'
import { MessageInput } from './message-input'

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
          className="text-gray-500 hover:text-gray-700"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
      
      <div className="flex-1 overflow-auto p-4 space-y-6 max-h-[calc(100vh-180px)]">
        {/* Master message */}
        <div className="flex gap-3">
          <Avatar className="h-10 w-10">
            <AvatarImage src="/placeholder.svg" />
            <AvatarFallback>KP</AvatarFallback>
          </Avatar>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium text-gray-900">Kenny Park</span>
              <span className="text-sm text-gray-500">11:55</span>
            </div>
            <p className="text-gray-900">
              Really need to give some kudos to @Emily for helping out with the new influx of tweets yesterday.
              People are really really excited about yesterday's announcement.
            </p>
          </div>
        </div>

        {/* Replies section */}
        <div className="relative">
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium text-gray-500">2 Replies</span>
            <div className="flex-1 h-px bg-gray-200 mr-[5%]"></div>
          </div>
          
          <div className="mt-6 space-y-4">
            <div className="flex gap-3">
              <Avatar className="h-8 w-8">
                <AvatarImage src="/placeholder.svg" />
                <AvatarFallback>PL</AvatarFallback>
              </Avatar>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-900">Paul Leung</span>
                  <span className="text-sm text-gray-500">11:56</span>
                </div>
                <p className="text-gray-900">No! It was my pleasure! Great to see the enthusiasm out there.</p>
              </div>
            </div>

            <div className="flex gap-3">
              <Avatar className="h-8 w-8">
                <AvatarImage src="/placeholder.svg" />
                <AvatarFallback>EA</AvatarFallback>
              </Avatar>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-900">Emily Anderson</span>
                  <span className="text-sm text-gray-500">11:57</span>
                </div>
                <p className="text-gray-900">Thanks everyone! Let's keep this momentum going! 🚀</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <MessageInput />
    </div>
  )
}

