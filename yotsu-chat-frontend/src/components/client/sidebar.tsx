'use client'

import { Hash, ChevronRight } from 'lucide-react'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/client/avatar'
import { useState } from 'react'

interface SidebarProps {
  activeView: {
    type: 'channel' | 'dm';
    data: any;
  }
  onChannelSelect: (channel: string) => void
  onDMSelect: (user: { name: string; avatar: string; initials: string }) => void
  onProfileClick: (profile: { name: string; avatar: string; initials: string }) => void
}

export function Sidebar({ activeView, onChannelSelect, onDMSelect, onProfileClick }: SidebarProps) {
  const [isChannelsExpanded, setIsChannelsExpanded] = useState(true)
  const [isDMsExpanded, setIsDMsExpanded] = useState(true)

  const isChannelActive = (channel: string) => 
    activeView.type === 'channel' && activeView.data === channel

  const isDMActive = (name: string) =>
    activeView.type === 'dm' && activeView.data.name === name

  return (
    <div className="w-60 bg-[#2c0929] border-r border-[#5a3c5a] flex flex-col h-screen overflow-hidden">
      <div className="p-4 border-b border-[#5a3c5a]">
        <h2 className="text-lg font-semibold">
          Yotsu Chat
        </h2>
      </div>
      
      <div className="flex-1 overflow-y-auto">
        <div className="p-2">
          <button className="w-full text-left p-2 rounded-md hover:bg-[#5a3c5a] text-[#dfdfdf]">
            🧵 Threads
          </button>
          <button className="w-full text-left p-2 rounded-md hover:bg-[#5a3c5a] text-[#dfdfdf]">
            💬 All DMs
          </button>
          <button className="w-full text-left p-2 rounded-md hover:bg-[#5a3c5a] text-[#dfdfdf]">
            📝 Drafts
          </button>
        </div>

        <div className="p-2">
          <button 
            onClick={() => setIsChannelsExpanded(!isChannelsExpanded)}
            className="w-full flex items-center gap-2 p-2 text-sm text-[#dfdfdf] group"
          >
            <span>Channels</span>
            <div className="w-5 h-5 rounded-full hover:bg-[#5a3c5a] flex items-center justify-center">
              <ChevronRight className={`h-4 w-4 transform transition-transform ${isChannelsExpanded ? 'rotate-90' : ''}`} />
            </div>
          </button>
          {isChannelsExpanded ? (
            <>
              <button 
                onClick={() => onChannelSelect('design-team')}
                className={`w-full text-left p-2 rounded-md ${
                  isChannelActive('design-team') 
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
                  isChannelActive('social-media') 
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
                  isChannelActive('team-finance') 
                    ? 'bg-[#4a1d49] text-white' 
                    : 'text-[#dfdfdf] hover:bg-[#5a3c5a]'
                }`}
              >
                <Hash className="inline-block h-4 w-4 mr-2" />
                team-finance
              </button>
            </>
          ) : (
            isChannelActive('social-media') && (
              <button 
                onClick={() => onChannelSelect('social-media')}
                className="w-full text-left p-2 rounded-md bg-[#4a1d49] text-white"
              >
                <Hash className="inline-block h-4 w-4 mr-2" />
                social-media
              </button>
            )
          )}
        </div>

        <div className="p-2">
          <button 
            onClick={() => setIsDMsExpanded(!isDMsExpanded)}
            className="w-full flex items-center gap-2 p-2 text-sm text-[#dfdfdf] group"
          >
            <span>Direct messages</span>
            <div className="w-5 h-5 rounded-full hover:bg-[#5a3c5a] flex items-center justify-center">
              <ChevronRight className={`h-4 w-4 transform transition-transform ${isDMsExpanded ? 'rotate-90' : ''}`} />
            </div>
          </button>
          {isDMsExpanded ? (
            <>
              {[
                { name: "Will Rodrigues", initials: "WR" },
                { name: "Emily Anderson", initials: "EA" },
                { name: "Kenny Park", initials: "KP" }
              ].map((user) => (
                <button 
                  key={user.name}
                  className={`w-full text-left p-2 rounded-md flex items-center gap-2 ${
                    isDMActive(user.name) 
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
            activeView.type === 'dm' && (
              <button 
                className="w-full text-left p-2 rounded-md bg-[#4a1d49] flex items-center gap-2"
                onClick={() => onDMSelect(activeView.data)}
              >
                <Avatar 
                  className="h-6 w-6"
                  onClick={(e) => {
                    e.stopPropagation()
                    onProfileClick(activeView.data)
                  }}
                >
                  <AvatarImage src={activeView.data.avatar} />
                  <AvatarFallback>{activeView.data.initials}</AvatarFallback>
                </Avatar>
                <span className="text-white">{activeView.data.name}</span>
              </button>
            )
          )}
        </div>
      </div>
    </div>
  )
}

