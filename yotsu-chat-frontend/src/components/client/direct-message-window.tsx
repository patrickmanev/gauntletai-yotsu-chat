import { Avatar, AvatarFallback, AvatarImage } from '@/components/client/avatar'
import { MessageInput } from './message-input'

interface DirectMessageWindowProps {
  user: {
    name: string;
    avatar: string;
    initials: string;
  }
  onProfileClick: (profile: { name: string; avatar: string; initials: string }) => void
  onThreadSelect: (id: string) => void
}

export function DirectMessageWindow({ user, onProfileClick, onThreadSelect }: DirectMessageWindowProps) {
  return (
    <div className="flex-1 flex flex-col bg-white text-gray-900">
      <div className="p-4 border-b border-gray-200 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <button 
            onClick={() => onProfileClick(user)}
            className="flex items-center"
          >
            <h1 className="text-xl font-semibold">{user.name}</h1>
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto p-4 space-y-6">
        <div className="flex gap-3" onClick={() => onThreadSelect('dm-1')}>
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
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium">{user.name}</span>
              <span className="text-sm text-gray-500">11:55</span>
            </div>
            <p className="text-gray-900">
              Hey! Thanks for reaching out. I'd love to discuss the project details.
            </p>
          </div>
        </div>
      </div>
      <MessageInput placeholder={`Message ${user.name}`} />
    </div>
  )
}

