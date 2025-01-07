'use client'

import * as React from 'react'
import { Button } from "@/components/ui/button"
import { Hash } from 'lucide-react'
import { usePathname, useRouter } from 'next/navigation'

interface Channel {
  channel_id: number
  name: string
  type: string
  created_at: string
}

interface ChannelListProps {
  onChannelSelect: (channel: Channel) => void
}

export function ChannelList({ onChannelSelect }: ChannelListProps) {
  const [channels, setChannels] = React.useState<Channel[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const pathname = usePathname()
  const router = useRouter()

  React.useEffect(() => {
    async function fetchChannels() {
      try {
        const response = await fetch('/api/channels')
        if (!response.ok) throw new Error('Failed to fetch channels')
        const data = await response.json()
        setChannels(data)
      } catch (error) {
        console.error('Error fetching channels:', error)
      } finally {
        setIsLoading(false)
      }
    }

    fetchChannels()
  }, [])

  if (isLoading) {
    return <div className="space-y-1">Loading channels...</div>
  }

  return (
    <div className="space-y-1">
      {channels.map((channel) => (
        <Button
          key={channel.channel_id}
          variant="ghost"
          className={`w-full justify-start ${
            pathname === `/channels/${channel.channel_id}`
              ? 'bg-white/10 text-white' 
              : 'text-white/70 hover:bg-white/10 hover:text-white'
          }`}
          onClick={() => {
            router.push(`/channels/${channel.channel_id}`)
            onChannelSelect(channel)
          }}
        >
          <Hash className="mr-2 h-4 w-4" />
          {channel.name}
        </Button>
      ))}
    </div>
  )
}

