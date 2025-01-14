import { MessageInput } from './message-input'
import { Message } from './message'

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
            className="text-xl font-semibold px-3 py-1 rounded-md hover:bg-gray-200 transition-colors"
          >
            {user.name}
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        <Message 
          user={user}
          timestamp="11:55"
          content="Hey! Thanks for reaching out. I'd love to discuss the project details."
          onProfileClick={onProfileClick}
          onClick={() => onThreadSelect('dm-1')}
        />
      </div>
      <MessageInput placeholder={`Message ${user.name}`} />
    </div>
  )
}

