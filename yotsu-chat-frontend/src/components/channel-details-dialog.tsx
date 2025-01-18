import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { DisplayName } from './display-name'

import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger,
  DropdownMenuSeparator
} from "@/components/ui/dropdown-menu"
import { MoreHorizontal, UserPlus } from 'lucide-react'
import { useState } from "react"
import { AddMemberDialog } from "./add-member-dialog"

interface ChannelDetailsDialogProps {
  channel: string
  isOpen: boolean
  onOpenChange: (open: boolean) => void
}

export function ChannelDetailsDialog({
  channel,
  isOpen,
  onOpenChange
}: ChannelDetailsDialogProps) {
  const [isAddMemberOpen, setIsAddMemberOpen] = useState(false)
  
  // Placeholder data
  const members = [
    { name: "Emily Anderson", initials: "EA", role: "Owner" },
    { name: "Kenny Park", initials: "KP", role: "Admin" },
    { name: "Paul Leung", initials: "PL", role: null },
    { name: "Sarah Chen", initials: "SC", role: "Admin" },
    { name: "Will Rodrigues", initials: "WR", role: null },
  ]

  return (
    <>
      <Dialog open={isOpen} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[425px] rounded-lg">
          <DialogHeader>
            <DialogTitle>#{channel}</DialogTitle>
            <div className="text-sm text-muted-foreground">
              Created by Emily Anderson at March 15, 2024
            </div>
          </DialogHeader>
          <div className="py-4">
            <h3 className="text-sm font-medium mb-3">Members</h3>
            <div className="space-y-2">
              {members.map((member) => (
                <div 
                  key={member.name} 
                  className="flex items-center justify-between group hover:bg-gray-50 rounded-md p-2 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Avatar className="h-6 w-6">
                      <AvatarImage src="/placeholder.svg" />
                      <AvatarFallback>{member.initials}</AvatarFallback>
                    </Avatar>
                    <DisplayName name={member.name} isOnline={true} />
                  </div>
                  <div className="flex items-center gap-2">
                    {member.role && (
                      <span className="text-sm text-muted-foreground">
                        {member.role}
                      </span>
                    )}
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button className="opacity-0 group-hover:opacity-100 p-1 rounded-md hover:bg-gray-200 transition-all">
                          <MoreHorizontal className="h-4 w-4 text-gray-500" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-48">
                        <DropdownMenuItem
                          onClick={() => {
                            // Handle transfer ownership
                          }}
                        >
                          Transfer ownership
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => {
                            // Handle promote to admin
                          }}
                        >
                          Promote to admin
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => {
                            // Handle demote to member
                          }}
                        >
                          Demote to member
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          className="text-red-600"
                          onClick={() => {
                            // Handle remove from channel
                          }}
                        >
                          Remove from channel
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              ))}
            </div>
            <button
              onClick={() => setIsAddMemberOpen(true)}
              className="mt-4 w-full flex items-center justify-center gap-2 p-2 rounded-md text-sm hover:bg-green-100 border border-gray-200 transition-colors"
            >
              <UserPlus className="h-4 w-4" />
              Add member
            </button>
          </div>
        </DialogContent>
      </Dialog>

      <AddMemberDialog 
        isOpen={isAddMemberOpen}
        onOpenChange={setIsAddMemberOpen}
      />
    </>
  )
}