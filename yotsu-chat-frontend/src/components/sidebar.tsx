'use client'

import { useState } from 'react'
import { DirectMessagesList } from './direct-messages-list'
import { ChannelsList } from './channels-list'

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

  const activeChannel = activeView.type === 'channel' ? activeView.data : null
  const activeDM = activeView.type === 'dm' ? activeView.data : null

  return (
    <div className="w-60 bg-[#2c0929] border-r border-[#5a3c5a] flex flex-col h-screen overflow-hidden">
      <div className="p-4 border-b border-[#5a3c5a]">
        <h2 className="text-lg font-semibold">
          Yotsu Chat
        </h2>
      </div>
      
      <div className="flex-1 overflow-y-auto">
        <ChannelsList 
          isExpanded={isChannelsExpanded}
          setIsExpanded={setIsChannelsExpanded}
          activeChannel={activeChannel}
          onChannelSelect={onChannelSelect}
        />

        <DirectMessagesList 
          isExpanded={isDMsExpanded}
          setIsExpanded={setIsDMsExpanded}
          activeDM={activeDM}
          onDMSelect={onDMSelect}
          onProfileClick={onProfileClick}
        />
      </div>
    </div>
  )
}

