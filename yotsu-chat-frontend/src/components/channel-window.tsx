import { MoreHorizontal } from 'lucide-react'
import { MessageInput } from './message-input'
import { Message } from './message'
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu'
import { useState } from 'react'
import { ChannelDetailsDialog } from './channel-details-dialog'

interface ChannelWindowProps {
  channel: string;
  onThreadSelect: (id: string) => void;
  onProfileClick: (profile: { name: string; avatar: string; initials: string }) => void;
}

export function ChannelWindow({ channel, onThreadSelect, onProfileClick }: ChannelWindowProps) {
  const [isDetailsOpen, setIsDetailsOpen] = useState(false)

  return (
    <div className="flex-1 flex flex-col bg-white text-gray-900">
      <div className="p-4 border-b border-gray-200 flex justify-between items-center">
        <button 
          onClick={() => setIsDetailsOpen(true)}
          className="text-xl font-semibold px-3 py-1 rounded-md hover:bg-gray-200 transition-colors"
        >
          #{channel}
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="p-1.5 rounded-lg hover:bg-gray-100">
              <MoreHorizontal className="h-5 w-5 text-gray-600" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem className="text-red-600">
              Leave channel
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="flex-1 overflow-auto">
        <Message 
          user={{
            name: "Kenny Park",
            avatar: "/placeholder.svg",
            initials: "KP"
          }}
          timestamp="11:55"
          content="Really need to give some kudos to @Emily for helping out with the new influx of tweets yesterday. People are really really excited about yesterday's announcement."
          onProfileClick={onProfileClick}
          onClick={() => onThreadSelect('1')}
        />
        <Message 
          user={{
            name: "Paul Leung",
            avatar: "/placeholder.svg",
            initials: "PL"
          }}
          timestamp="11:56"
          content="No! It was my pleasure! Great to see the enthusiasm out there."
          onProfileClick={onProfileClick}
          onClick={() => onThreadSelect('2')}
        />
      </div>
      <MessageInput placeholder={`Message #${channel}`} />

      <ChannelDetailsDialog 
        channel={channel}
        isOpen={isDetailsOpen}
        onOpenChange={setIsDetailsOpen}
      />
    </div>
  )
}

