'use client'

import { useState } from 'react'
import { Sidebar } from '@/components/client/sidebar'
import { TopBar } from '@/components/client/top-bar'
import { ThreadPanel } from '@/components/client/thread-panel'
import { ProfilePanel } from '@/components/client/profile-panel'
import { DirectMessageWindow } from '@/components/client/direct-message-window'
import { ChannelWindow } from '@/components/client/channel-window'

type Channel = string
type ThreadId = string
type UserProfile = {
  name: string;
  avatar: string;
  initials: string;
}

type ActiveView = {
  type: 'channel' | 'dm';
  data: Channel | UserProfile;
}

type ActivePanel = {
  type: 'thread' | 'profile' | null;
  data: ThreadId | UserProfile | null;
}

export default function Layout() {
  const [activeView, setActiveView] = useState<ActiveView>({ type: 'channel', data: 'social-media' })
  const [activePanel, setActivePanel] = useState<ActivePanel>({ type: null, data: null })

  return (
    <div className="flex h-screen bg-[#2c0929] text-white">
      <Sidebar 
        activeView={activeView}
        onChannelSelect={(channel: Channel) => {
          setActiveView({ type: 'channel', data: channel })
          setActivePanel({ type: null, data: null })
        }}
        onDMSelect={(user: UserProfile) => {
          setActiveView({ type: 'dm', data: user })
          setActivePanel({ type: null, data: null })
        }}
        onProfileClick={(profile: UserProfile) => {
          setActivePanel({ type: 'profile', data: profile })
        }}
      />
      <div className="flex-1 flex flex-col">
        <TopBar />
        <div className="flex-1 flex">
          {activeView.type === 'channel' ? (
            <ChannelWindow 
              channel={activeView.data as Channel}
              onThreadSelect={(id: ThreadId) => {
                setActivePanel({ type: 'thread', data: id })
              }}
              onProfileClick={(profile: UserProfile) => {
                setActivePanel({ type: 'profile', data: profile })
              }}
            />
          ) : (
            <DirectMessageWindow 
              user={activeView.data as UserProfile}
              onThreadSelect={(id: ThreadId) => {
                setActivePanel({ type: 'thread', data: id })
              }}
              onProfileClick={(profile: UserProfile) => {
                setActivePanel({ type: 'profile', data: profile })
              }}
            />
          )}
          {activePanel.type === 'thread' && (
            <ThreadPanel 
              threadId={activePanel.data as ThreadId} 
              onClose={() => setActivePanel({ type: null, data: null })}
            />
          )}
          {activePanel.type === 'profile' && (
            <ProfilePanel 
              profile={activePanel.data as UserProfile}
              onClose={() => setActivePanel({ type: null, data: null })}
            />
          )}
        </div>
      </div>
    </div>
  )
}

