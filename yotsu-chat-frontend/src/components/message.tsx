import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { MessageSquare, Smile, Pencil, Trash2 } from 'lucide-react'

interface MessageProps {
  user: {
    name: string;
    avatar: string;
    initials: string;
  }
  timestamp: string;
  content: string;
  onProfileClick: (profile: { name: string; avatar: string; initials: string }) => void;
  onClick?: () => void; // For thread selection
  isInThread?: boolean;
}

export function Message({ user, timestamp, content, onProfileClick, onClick, isInThread = false }: MessageProps) {
  return (
    <div 
      className="group/message w-full hover:bg-[#f8f8f8] transition-colors px-4 py-2 cursor-pointer"
    >
      <div className="flex gap-3 items-start">
        <button 
          onClick={(e) => {
            e.stopPropagation()
            onProfileClick(user)
          }}
        >
          <Avatar className="h-10 w-10">
            <AvatarImage src={user.avatar} />
            <AvatarFallback>{user.initials}</AvatarFallback>
          </Avatar>
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-gray-900">{user.name}</span>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">{timestamp}</span>
              <div className="hidden group-hover/message:flex items-center gap-1">
                <button 
                  onClick={(e) => {
                    e.stopPropagation()
                    // Handle edit
                  }}
                  className="p-1 rounded-md hover:bg-green-100 transition-colors"
                >
                  <Pencil className="h-3.5 w-3.5 text-gray-500" />
                </button>
                <button 
                  onClick={(e) => {
                    e.stopPropagation()
                    // Handle delete
                  }}
                  className="p-1 rounded-md hover:bg-red-100 transition-colors"
                >
                  <Trash2 className="h-3.5 w-3.5 text-gray-500" />
                </button>
              </div>
            </div>
          </div>
          <p className="text-gray-900 mb-2">{content}</p>
          
          {/* Action buttons - visible only on message hover */}
          <div className="flex gap-2 hidden group-hover/message:flex">
            <button 
              onClick={(e) => {
                e.stopPropagation()
                // Add emoji reaction handler here
              }}
              className="inline-flex items-center px-2.5 py-1.5 border border-gray-200 rounded-md text-sm text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <Smile className="h-4 w-4 mr-1" />
              React
            </button>
            {!isInThread && (
              <button 
                onClick={(e) => {
                  e.stopPropagation()
                  if (onClick) onClick()
                }}
                className="inline-flex items-center px-2.5 py-1.5 border border-gray-200 rounded-md text-sm text-gray-700 hover:bg-gray-50 transition-colors"
              >
                <MessageSquare className="h-4 w-4 mr-1" />
                Reply in thread
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

