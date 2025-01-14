import { ChevronRight, Plus, X, Check, Search } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useState } from 'react'

interface DirectMessagesListProps {
  isExpanded: boolean
  setIsExpanded: (value: boolean) => void
  activeDM: { name: string; avatar: string; initials: string } | null
  onDMSelect: (user: { name: string; avatar: string; initials: string }) => void
  onProfileClick: (profile: { name: string; avatar: string; initials: string }) => void
}

export function DirectMessagesList({
  isExpanded,
  setIsExpanded,
  activeDM,
  onDMSelect,
  onProfileClick
}: DirectMessagesListProps) {
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  return (
    <>
      <div className="p-2">
        <button 
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full flex items-center gap-2 p-2 text-sm text-[#dfdfdf] group"
        >
          <span>Direct messages</span>
          <div className="w-5 h-5 rounded-full hover:bg-[#5a3c5a] flex items-center justify-center">
            <ChevronRight className={`h-4 w-4 transform transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
          </div>
        </button>
        {isExpanded ? (
          <>
            {[
              { name: "Will Rodrigues", initials: "WR" },
              { name: "Emily Anderson", initials: "EA" },
              { name: "Kenny Park", initials: "KP" }
            ].map((user) => (
              <button 
                key={user.name}
                className={`w-full text-left p-2 rounded-md flex items-center gap-2 ${
                  activeDM?.name === user.name 
                    ? 'bg-[#4a1d49] text-white' 
                    : 'text-[#dfdfdf] hover:bg-[#5a3c5a]'
                }`}
                onClick={() => onDMSelect({
                  ...user,
                  avatar: "/placeholder.svg"
                })}
              >
                <Avatar 
                  className="h-6 w-6"
                  onClick={(e) => {
                    e.stopPropagation()
                    onProfileClick({
                      ...user,
                      avatar: "/placeholder.svg"
                    })
                  }}
                >
                  <AvatarImage src="/placeholder.svg" />
                  <AvatarFallback>{user.initials}</AvatarFallback>
                </Avatar>
                <span>{user.name}</span>
              </button>
            ))}
          </>
        ) : (
          activeDM && (
            <button 
              className="w-full text-left p-2 rounded-md bg-[#4a1d49] flex items-center gap-2"
              onClick={() => onDMSelect(activeDM)}
            >
              <Avatar 
                className="h-6 w-6"
                onClick={(e) => {
                  e.stopPropagation()
                  onProfileClick(activeDM)
                }}
              >
                <AvatarImage src={activeDM.avatar} />
                <AvatarFallback>{activeDM.initials}</AvatarFallback>
              </Avatar>
              <span className="text-white">{activeDM.name}</span>
            </button>
          )
        )}
        <button 
          onClick={() => setIsDialogOpen(true)}
          className="p-2 rounded-md text-[#dfdfdf] hover:bg-[#5a3c5a] mt-2"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-[425px] rounded-lg [&>button]:hidden">
          <DialogHeader>
            <DialogTitle>DM another user</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
              <Input
                placeholder="Search user"
                className="w-full pl-9"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setIsDialogOpen(false)}
              className="p-2 rounded-md border border-gray-200 hover:bg-red-100 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
            <button
              onClick={() => {
                // Handle confirmation
                setIsDialogOpen(false)
              }}
              className="p-2 rounded-md border border-gray-200 hover:bg-green-100 transition-colors"
            >
              <Check className="h-4 w-4" />
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

