'use client'

import { useState } from 'react'
import { Sidebar } from '@/components/sidebar'
import { TopBar } from '@/components/top-bar'
import { ThreadPanel } from '@/components/thread-panel'
import { ProfilePanel } from '@/components/profile-panel'
import { DirectMessageWindow } from '@/components/direct-message-window'
import { ChannelWindow } from '@/components/channel-window'

// Define types for our state management
type User = {
  name: string;
  avatar: string;
  initials: string;
}

type ActiveView = {
  type: 'channel' | 'dm';
  data: string | User;
}

type SidePanel = {
  type: 'thread' | 'profile' | null;
  data: string | User | null;
}

export default function Layout() {
  // State for managing active view (channel or DM)
  const [activeView, setActiveView] = useState<ActiveView>({ 
    type: 'channel', 
    data: 'social-media'
  })

  // State for managing side panel (thread or profile)
  const [sidePanel, setSidePanel] = useState<SidePanel>({ 
    type: null, 
    data: null 
  })

  // Handler for profile clicks
  const handleProfileClick = (profile: User) => {
    setSidePanel({ 
      type: 'profile', 
      data: profile 
    })
  }

  // Handler for thread selection
  const handleThreadSelect = (threadId: string) => {
    setSidePanel({ 
      type: 'thread', 
      data: threadId 
    })
  }

  // Handler for closing side panels
  const handlePanelClose = () => {
    setSidePanel({ 
      type: null, 
      data: null 
    })
  }

  return (
    <div className="flex h-screen bg-[#2c0929] text-white">
      {/* Sidebar */}
      <Sidebar 
        activeView={activeView}
        onChannelSelect={(channel: string) => {
          setActiveView({ type: 'channel', data: channel })
          setSidePanel({ type: null, data: null })
        }}
        onDMSelect={(user: User) => {
          setActiveView({ type: 'dm', data: user })
          setSidePanel({ type: null, data: null })
        }}
        onProfileClick={handleProfileClick}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col">
        <TopBar />
        <div className="flex-1 flex">
          {/* Main Window (Channel or DM) */}
          {activeView.type === 'channel' ? (
            <ChannelWindow 
              channel={activeView.data as string}
              onThreadSelect={handleThreadSelect}
              onProfileClick={handleProfileClick}
            />
          ) : (
            <DirectMessageWindow 
              user={activeView.data as User}
              onThreadSelect={handleThreadSelect}
              onProfileClick={handleProfileClick}
            />
          )}

          {/* Side Panels (Thread or Profile) */}
          {sidePanel.type === 'thread' && (
            <ThreadPanel 
              threadId={sidePanel.data as string}
              onClose={handlePanelClose}
            />
          )}
          {sidePanel.type === 'profile' && (
            <ProfilePanel 
              profile={sidePanel.data as User}
              onClose={handlePanelClose}
            />
          )}
        </div>
      </div>
    </div>
  )
}

