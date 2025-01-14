import { Hash, ChevronRight, Plus, Check, X, Search, Users } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { useState } from 'react'

interface ChannelsListProps { 
  isExpanded: boolean
  setIsExpanded: (value: boolean) => void
  activeChannel: string | null
  onChannelSelect: (channel: string) => void
}

export function ChannelsList({ 
  isExpanded, 
  setIsExpanded, 
  activeChannel, 
  onChannelSelect 
}: ChannelsListProps) {
  const [isJoinDialogOpen, setIsJoinDialogOpen] = useState(false)
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null)
  const [isPublic, setIsPublic] = useState(true)
  const [selectedUsers, setSelectedUsers] = useState<Array<{
    name: string;
    avatar: string;
    initials: string;
  }>>([])

  const publicChannels = [
    'announcements',
    'general',
    'design-team',
    'marketing',
    'social-media',
    'team-finance',
    'watercooler'
  ]

  return (
    <div className="p-2">
      <button 
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 p-2 text-sm text-[#dfdfdf] group"
      >
        <span>Channels</span>
        <div className="w-5 h-5 rounded-full hover:bg-[#5a3c5a] flex items-center justify-center">
          <ChevronRight className={`h-4 w-4 transform transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
        </div>
      </button>
      {isExpanded ? (
        <>
          <button 
            onClick={() => onChannelSelect('design-team')}
            className={`w-full text-left p-2 rounded-md ${
              activeChannel === 'design-team'
                ? 'bg-[#4a1d49] text-white' 
                : 'text-[#dfdfdf] hover:bg-[#5a3c5a]'
            }`}
          >
            <Hash className="inline-block h-4 w-4 mr-2" />
            design-team
          </button>
          <button 
            onClick={() => onChannelSelect('social-media')}
            className={`w-full text-left p-2 rounded-md ${
              activeChannel === 'social-media'
                ? 'bg-[#4a1d49] text-white' 
                : 'text-[#dfdfdf] hover:bg-[#5a3c5a]'
            }`}
          >
            <Hash className="inline-block h-4 w-4 mr-2" />
            social-media
          </button>
          <button 
            onClick={() => onChannelSelect('team-finance')}
            className={`w-full text-left p-2 rounded-md ${
              activeChannel === 'team-finance'
                ? 'bg-[#4a1d49] text-white' 
                : 'text-[#dfdfdf] hover:bg-[#5a3c5a]'
            }`}
          >
            <Hash className="inline-block h-4 w-4 mr-2" />
            team-finance
          </button>
        </>
      ) : (
        activeChannel && (
          <button 
            onClick={() => onChannelSelect(activeChannel)}
            className="w-full text-left p-2 rounded-md bg-[#4a1d49] text-white"
          >
            <Hash className="inline-block h-4 w-4 mr-2" />
            {activeChannel}
          </button>
        )
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="p-2 rounded-md text-[#dfdfdf] hover:bg-[#5a3c5a] mt-2">
            <Plus className="h-4 w-4" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" alignOffset={-2}>
          <DropdownMenuItem onSelect={() => setIsJoinDialogOpen(true)}>
            Join channel
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setIsCreateDialogOpen(true)}>
            Create channel
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Join Channel Dialog */}
      <Dialog open={isJoinDialogOpen} onOpenChange={setIsJoinDialogOpen}>
        <DialogContent className="sm:max-w-[425px] rounded-lg [&>button]:hidden">
          <DialogHeader>
            <DialogTitle>All public channels</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <div className="relative mb-4">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
              <Input
                placeholder="Search channels"
                className="w-full pl-9"
              />
            </div>
            <div className="max-h-[240px] overflow-y-auto">
              {publicChannels.map((channel) => (
                <button
                  key={channel}
                  onClick={() => setSelectedChannel(channel)}
                  className={`w-full text-left p-2 rounded-md flex items-center gap-2 ${
                    selectedChannel === channel
                      ? 'bg-[#4a1d49] text-white'
                      : 'text-gray-900 hover:bg-gray-100'
                  }`}
                >
                  <Hash className="h-4 w-4" />
                  <span>{channel}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setIsJoinDialogOpen(false)
                setSelectedChannel(null)
              }}
              className="p-2 rounded-md border border-gray-200 hover:bg-red-100 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
            <button
              onClick={() => {
                if (selectedChannel) {
                  onChannelSelect(selectedChannel)
                }
                setIsJoinDialogOpen(false)
                setSelectedChannel(null)
              }}
              className="p-2 rounded-md border border-gray-200 hover:bg-green-100 transition-colors"
            >
              <Check className="h-4 w-4" />
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create Channel Dialog */}
      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent className="sm:max-w-[425px] rounded-lg [&>button]:hidden">
          <DialogHeader>
            <DialogTitle>Create channel</DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-6">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Channel type</Label>
                <div className="text-sm text-gray-500">
                  {isPublic ? 'Public' : 'Private'} channel
                </div>
              </div>
              <Switch
                checked={isPublic}
                onCheckedChange={setIsPublic}
              />
            </div>

            <div className="space-y-4">
              <Label>Add members</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
                <Input
                  placeholder="Search users"
                  className="w-full pl-9"
                />
              </div>
              
              <div className="space-y-2">
                {selectedUsers.map((user) => (
                  <div 
                    key={user.name}
                    className="flex items-center justify-between p-2 rounded-md bg-gray-50"
                  >
                    <div className="flex items-center gap-2">
                      <Avatar className="h-6 w-6">
                        <AvatarImage src={user.avatar} />
                        <AvatarFallback>{user.initials}</AvatarFallback>
                      </Avatar>
                      <span className="text-sm">{user.name}</span>
                    </div>
                    <button
                      onClick={() => setSelectedUsers(users => users.filter(u => u.name !== user.name))}
                      className="text-gray-500 hover:text-gray-700"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ))}
                {selectedUsers.length === 0 && (
                  <div className="flex items-center justify-center gap-2 p-4 text-sm text-gray-500">
                    <Users className="h-4 w-4" />
                    <span>No users added yet</span>
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setIsCreateDialogOpen(false)
                setSelectedUsers([])
                setIsPublic(true)
              }}
              className="p-2 rounded-md border border-gray-200 hover:bg-red-100 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
            <button
              onClick={() => {
                // Handle channel creation
                setIsCreateDialogOpen(false)
                setSelectedUsers([])
                setIsPublic(true)
              }}
              className="p-2 rounded-md border border-gray-200 hover:bg-green-100 transition-colors"
            >
              <Check className="h-4 w-4" />
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

