import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Search, Users, X, Check } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { useState } from "react"

interface AddMemberDialogProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
}

export function AddMemberDialog({
  isOpen,
  onOpenChange
}: AddMemberDialogProps) {
  const [selectedUsers, setSelectedUsers] = useState<Array<{
    name: string;
    avatar: string;
    initials: string;
  }>>([])

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px] rounded-lg [&>button]:hidden">
        <DialogHeader>
          <DialogTitle>Add member</DialogTitle>
        </DialogHeader>
        <div className="py-4 space-y-4">
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
                <span>No users selected</span>
              </div>
            )}
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={() => onOpenChange(false)}
            className="p-2 rounded-md border border-gray-200 hover:bg-red-100 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
          <button
            onClick={() => {
              // Handle adding members
              onOpenChange(false)
            }}
            className="p-2 rounded-md border border-gray-200 hover:bg-green-100 transition-colors"
          >
            <Check className="h-4 w-4" />
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

