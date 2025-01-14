import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { MoreHorizontal } from 'lucide-react'
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu'

interface MessageThreadProps {
  onThreadSelect: (id: string) => void
  onProfileClick: (profile: { name: string; avatar: string; initials: string }) => void
}

export function MessageThread({ onThreadSelect, onProfileClick }: MessageThreadProps) {
  return (
    <>
      <div className="p-4 border-b border-gray-200 flex justify-between items-center">
        <h1 className="text-xl font-semibold">#social-media</h1>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="p-1.5 rounded-lg hover:bg-gray-100">
              <MoreHorizontal className="h-5 w-5 text-gray-600" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem>
              Open channel details
            </DropdownMenuItem>
            <DropdownMenuItem className="text-red-600">
              Leave channel
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="p-4 space-y-6 bg-white text-gray-900">
        <div className="flex gap-3" onClick={() => onThreadSelect('1')}>
          <button 
            onClick={(e) => {
              e.stopPropagation()
              onProfileClick({
                name: "Kenny Park",
                avatar: "/placeholder.svg",
                initials: "KP"
              })
            }}
          >
            <Avatar className="h-10 w-10">
              <AvatarImage src="/placeholder.svg" />
              <AvatarFallback>KP</AvatarFallback>
            </Avatar>
          </button>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium">Kenny Park</span>
              <span className="text-sm text-gray-500">11:55</span>
            </div>
            <p className="text-gray-900">
              Really need to give some kudos to @Emily for helping out with the new influx of tweets yesterday.
              People are really really excited about yesterday's announcement.
            </p>
          </div>
        </div>

        <div className="flex gap-3" onClick={() => onThreadSelect('2')}>
          <button 
            onClick={(e) => {
              e.stopPropagation()
              onProfileClick({
                name: "Paul Leung",
                avatar: "/placeholder.svg",
                initials: "PL"
              })
            }}
          >
            <Avatar className="h-10 w-10">
              <AvatarImage src="/placeholder.svg" />
              <AvatarFallback>PL</AvatarFallback>
            </Avatar>
          </button>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium">Paul Leung</span>
              <span className="text-sm text-gray-500">11:56</span>
            </div>
            <p className="text-gray-900">
              No! It was my pleasure! Great to see the enthusiasm out there.
            </p>
          </div>
        </div>
      </div>
    </>
  )
}

