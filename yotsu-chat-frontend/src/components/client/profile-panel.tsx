import { X } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/client/avatar'

interface ProfilePanelProps {
  profile: {
    name: string;
    avatar: string;
    initials: string;
  }
  onClose: () => void
}

export function ProfilePanel({ profile, onClose }: ProfilePanelProps) {
  return (
    <div className="w-[400px] border-l border-gray-200 flex flex-col bg-white">
      <div className="h-[48px] p-3 border-b border-gray-200 flex justify-between items-center">
        <h2 className="font-semibold text-gray-900">Profile</h2>
        <button 
          onClick={onClose} 
          className="text-gray-500 hover:text-gray-700"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
      
      <div className="flex-1 overflow-auto">
        <div className="flex justify-center mt-12">
          <Avatar className="w-48 h-48 rounded-lg border-2 border-gray-500">
            <AvatarImage src={profile.avatar} />
            <AvatarFallback>{profile.initials}</AvatarFallback>
          </Avatar>
        </div>
        <div className="p-6">
          <h3 className="text-xl font-semibold text-gray-900">{profile.name}</h3>
        </div>
      </div>
    </div>
  )
}

