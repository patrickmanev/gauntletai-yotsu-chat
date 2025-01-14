import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { produce } from 'immer'

// -------------------------------------------------------------------
// 1) Types for our slices
// -------------------------------------------------------------------

type AuthSlice = {
  accessToken: string | null
  isAuthenticated: boolean
  userId: number | null
  login: (creds: { email: string; password: string }) => Promise<void>
  logout: () => void
  refreshTokens: () => Promise<void>
  setAccessToken: (token: string | null) => void
}

type PresenceSlice = {
  onlineUsers: Record<number, boolean>
  updatePresence: (userId: number, online: boolean) => void
}

type Channel = {
  channel_id: number
  name: string
  type: 'public' | 'private' | 'dm' | 'notes'
  // other channel fields as needed...
}

type ChannelsSlice = {
  channels: Record<number, Channel>
  listChannels: () => Promise<void>
  createChannel: (params: { name: string; type: 'public' | 'private' }) => Promise<void>
  refreshChannels: () => Promise<void> // For re-fetching entire channel list
  updateChannel: (channelId: number, payload: { name: string }) => Promise<void>
  handleJoinEvent: (channelId: number, joinedUserId: number) => void
  handleLeaveEvent: (channelId: number, leftUserId: number) => void
}

type Member = {
  user_id: number
  display_name: string
  role: string
  // other membership fields...
}

type ChannelMemberSlice = {
  membersByChannel: Record<number, Member[]>
  fetchChannelMembers: (channelId: number) => Promise<void>
  clearChannelMembers: (channelId: number) => void
}

type Message = {
  message_id: number
  channel_id: number
  user_id: number
  content: string
  created_at: string
  edited_at?: string | null
  display_name: string
  parent_id?: number | null
  has_reactions: boolean
}

type MessagesSlice = {
  messagesByChannel: Record<number, Message[]>
  fetchMessages: (channelId: number) => Promise<void>
  createMessage: (channelId: number, content: string) => Promise<void>
  updateMessage: (messageId: number, content: string) => Promise<void>
  deleteMessage: (messageId: number) => Promise<void>
  handleMessageCreated: (message: Message) => void
  handleMessageUpdated: (message: Message) => void
  handleMessageDeleted: (messageId: number, channelId: number) => void
}

type Reaction = {
  emoji: string
  count: number
  users: number[]
}

type ReactionsSlice = {
  // The store only fetches for messages that have has_reactions = true
  reactionsByMessage: Record<number, Reaction[]>
  fetchReactionsForMessage: (messageId: number) => Promise<void>
  handleReactionAdded: (messageId: number, payload: { emoji: string; user_id: number }) => void
  handleReactionRemoved: (messageId: number, payload: { emoji: string; user_id: number }) => void
}

// Combine all slices into a single store type
type AppStore = AuthSlice &
  PresenceSlice &
  ChannelsSlice &
  ChannelMemberSlice &
  MessagesSlice &
  ReactionsSlice

// -------------------------------------------------------------------
// 2) Slice Creators
// -------------------------------------------------------------------

// AUTH SLICE
// In practice, you’d replace console.log with real fetches to the backend
const createAuthSlice = (set: any, get: any): AuthSlice => ({
  accessToken: null,
  isAuthenticated: false,
  userId: null,

  login: async ({ email, password }) => {
    try {
      // Example for retrieving tokens from an /auth/login endpoint
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      })
      if (!response.ok) throw new Error('Failed to log in')

      // This is a simplified example. If 2FA is required, we'd handle temp_token logic, etc.
      const data = await response.json()

      // Suppose we received { access_token, refresh_token, user_id, etc. }
      if (data.access_token) {
        set((state: AuthSlice) => {
          state.accessToken = data.access_token
          state.isAuthenticated = true
          state.userId = data.user_id
        })
        // Store refresh token in localStorage
        if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token)
      }
    } catch (err) {
      console.error('Login error:', err)
      throw err
    }
  },

  logout: () => {
    set((state: AuthSlice) => {
      state.accessToken = null
      state.isAuthenticated = false
      state.userId = null
    })
    localStorage.removeItem('refresh_token')
  },

  refreshTokens: async () => {
    try {
      const storedRefreshToken = localStorage.getItem('refresh_token')
      if (!storedRefreshToken) throw new Error('No refresh token stored')
      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: storedRefreshToken })
      })
      if (!response.ok) throw new Error('Refresh token failed')
      const data = await response.json()

      set((state: AuthSlice) => {
        state.accessToken = data.access_token
        state.isAuthenticated = true
      })
      // Update the stored refresh token if the server returned a new one
      if (data.refresh_token) {
        localStorage.setItem('refresh_token', data.refresh_token)
      }
    } catch (err) {
      console.error('Token refresh error:', err)
      get().logout() // Force a logout or re-login flow
    }
  },

  setAccessToken: (token: string | null) => {
    set((state: AuthSlice) => {
      state.accessToken = token
      state.isAuthenticated = !!token
    })
  }
})

// PRESENCE SLICE
const createPresenceSlice = (set: any): PresenceSlice => ({
  onlineUsers: {},

  updatePresence: (userId, online) => {
    set(
      produce((draft: PresenceSlice) => {
        draft.onlineUsers[userId] = online
      })
    )
  }
})

// CHANNELS SLICE
const createChannelsSlice = (set: any, get: any): ChannelsSlice => ({
  channels: {},

  listChannels: async () => {
    try {
      const accessToken = get().accessToken
      if (!accessToken) return

      // Example call to GET /channels
      const resp = await fetch('/api/channels', {
        headers: { Authorization: `Bearer ${accessToken}` }
      })
      if (!resp.ok) throw new Error('Failed to list channels')
      const data: Channel[] = await resp.json()

      set(
        produce((draft: ChannelsSlice) => {
          draft.channels = data.reduce((map, ch) => {
            map[ch.channel_id] = ch
            return map
          }, {} as Record<number, Channel>)
        })
      )
    } catch (err) {
      console.error('listChannels error:', err)
    }
  },

  createChannel: async ({ name, type }) => {
    try {
      const accessToken = get().accessToken
      if (!accessToken) return

      // Example call to POST /channels
      const resp = await fetch('/api/channels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ name, type })
      })
      if (!resp.ok) throw new Error('Failed to create channel')
      const newChannel: Channel = await resp.json()

      // Now fetch additional details (or just rely on newChannel if the API returned full data)
      // But let's assume we want to fetch the entire channel just to be safe:
      const detailResp = await fetch(`/api/channels/${newChannel.channel_id}`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      })
      if (!detailResp.ok) throw new Error('Failed to fetch details of the new channel')
      const channelDetails: Channel = await detailResp.json()

      set(
        produce((draft: ChannelsSlice) => {
          draft.channels[channelDetails.channel_id] = channelDetails
        })
      )
    } catch (err) {
      console.error('createChannel error:', err)
    }
  },

  refreshChannels: async () => {
    // Re-fetch the entire channel list
    get().listChannels()
  },

  updateChannel: async (channelId, payload) => {
    try {
      const accessToken = get().accessToken
      if (!accessToken) return

      // Example call to PATCH /channels/{channelId}
      const resp = await fetch(`/api/channels/${channelId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify(payload)
      })
      if (!resp.ok) throw new Error('Failed to update channel')
      const updated: Channel = await resp.json()

      set(
        produce((draft: ChannelsSlice) => {
          draft.channels[channelId] = updated
        })
      )
    } catch (err) {
      console.error('updateChannel error:', err)
    }
  },

  handleJoinEvent: (channelId, joinedUserId) => {
    // If it's the current user, re-fetch channel list if not already in the store
    const userId = get().userId
    const channelInStore = !!get().channels[channelId]

    if (joinedUserId === userId && !channelInStore) {
      // Re-fetch the entire channel list
      get().refreshChannels()
    }
  },

  handleLeaveEvent: (channelId, leftUserId) => {
    const userId = get().userId
    const channelInStore = !!get().channels[channelId]

    // If it's the current user leaving, remove the channel from store or re-fetch
    if (leftUserId === userId && channelInStore) {
      // Simpler to re-fetch the entire channel list
      get().refreshChannels()
    }
  }
})

// CHANNEL MEMBERS SLICE
const createChannelMemberSlice = (set: any, get: any): ChannelMemberSlice => ({
  membersByChannel: {},

  fetchChannelMembers: async (channelId) => {
    try {
      const accessToken = get().accessToken
      if (!accessToken) return

      const resp = await fetch(`/api/members/${channelId}`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      })
      if (!resp.ok) throw new Error('Failed to fetch channel members')
      const members: Member[] = await resp.json()

      set(
        produce((draft: ChannelMemberSlice) => {
          draft.membersByChannel[channelId] = members
        })
      )
    } catch (err) {
      console.error('fetchChannelMembers error:', err)
    }
  },

  clearChannelMembers: (channelId) => {
    set(
      produce((draft: ChannelMemberSlice) => {
        delete draft.membersByChannel[channelId]
      })
    )
  }
})

// MESSAGES SLICE
const createMessagesSlice = (set: any, get: any): MessagesSlice => ({
  messagesByChannel: {},

  fetchMessages: async (channelId) => {
    try {
      const accessToken = get().accessToken
      if (!accessToken) return

      // Example call to GET /messages/channels/{channel_id}
      const resp = await fetch(`/api/messages/channels/${channelId}`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      })
      if (!resp.ok) throw new Error('Failed to fetch messages')
      const msgs: Message[] = await resp.json()

      set(
        produce((draft: MessagesSlice) => {
          draft.messagesByChannel[channelId] = msgs
        })
      )
    } catch (err) {
      console.error('fetchMessages error:', err)
    }
  },

  createMessage: async (channelId, content) => {
    try {
      const accessToken = get().accessToken
      if (!accessToken) return

      const resp = await fetch('/api/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ channel_id: channelId, content: content })
      })
      if (!resp.ok) throw new Error('createMessage failed')
      const newMsg: Message = await resp.json()

      // Insert into store
      set(
        produce((draft: MessagesSlice) => {
          if (!draft.messagesByChannel[channelId]) draft.messagesByChannel[channelId] = []
          draft.messagesByChannel[channelId].push(newMsg)
        })
      )
    } catch (err) {
      console.error('createMessage error:', err)
    }
  },

  updateMessage: async (messageId, content) => {
    try {
      const accessToken = get().accessToken
      if (!accessToken) return

      const resp = await fetch(`/api/messages/${messageId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ content })
      })
      if (!resp.ok) throw new Error('Failed to update message')
      const updatedMsg: Message = await resp.json()

      set(
        produce((draft: MessagesSlice) => {
          const channelMessages = draft.messagesByChannel[updatedMsg.channel_id]
          if (channelMessages) {
            const idx = channelMessages.findIndex((m) => m.message_id === messageId)
            if (idx >= 0) {
              channelMessages[idx] = updatedMsg
            }
          }
        })
      )
    } catch (err) {
      console.error('updateMessage error:', err)
    }
  },

  deleteMessage: async (messageId) => {
    try {
      const accessToken = get().accessToken
      if (!accessToken) return

      const resp = await fetch(`/api/messages/${messageId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${accessToken}` }
      })
      if (!resp.ok) throw new Error('Failed to delete message')

      // If successful, the server returns 204
      // We can remove from store
      // But we also expect a "message.deleted" broadcast from the WS if we have that open
      // For immediate UI, we remove it from local store:
      set(
        produce((draft: MessagesSlice) => {
          // This is naive; we must find the channel in which the message resides
          for (const [chid, msgs] of Object.entries(draft.messagesByChannel)) {
            draft.messagesByChannel[+chid] = msgs.filter((m) => m.message_id !== messageId)
          }
        })
      )
    } catch (err) {
      console.error('deleteMessage error:', err)
    }
  },

  handleMessageCreated: (message) => {
    set(
      produce((draft: MessagesSlice) => {
        const { channel_id } = message
        if (!draft.messagesByChannel[channel_id]) draft.messagesByChannel[channel_id] = []
        const exists = draft.messagesByChannel[channel_id].some(
          (m) => m.message_id === message.message_id
        )
        if (!exists) {
          draft.messagesByChannel[channel_id].push(message)
        }
      })
    )
  },

  handleMessageUpdated: (message) => {
    set(
      produce((draft: MessagesSlice) => {
        const { channel_id } = message
        const channelMsgs = draft.messagesByChannel[channel_id]
        if (!channelMsgs) return
        const idx = channelMsgs.findIndex((m) => m.message_id === message.message_id)
        if (idx >= 0) {
          channelMsgs[idx] = message
        }
      })
    )
  },

  handleMessageDeleted: (messageId, channelId) => {
    set(
      produce((draft: MessagesSlice) => {
        const channelMsgs = draft.messagesByChannel[channelId]
        if (!channelMsgs) return
        draft.messagesByChannel[channelId] = channelMsgs.filter((m) => m.message_id !== messageId)
      })
    )
  }
})

// REACTIONS SLICE
const createReactionsSlice = (set: any, get: any): ReactionsSlice => ({
  reactionsByMessage: {},

  fetchReactionsForMessage: async (messageId: number) => {
    try {
      const accessToken = get().accessToken
      if (!accessToken) return

      // GET /reactions/messages/{message_id}
      const resp = await fetch(`/api/reactions/messages/${messageId}`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      })
      if (!resp.ok) throw new Error('Failed to fetch reactions')
      const data: Reaction[] = await resp.json()

      set(
        produce((draft: ReactionsSlice) => {
          draft.reactionsByMessage[messageId] = data
        })
      )
    } catch (err) {
      console.error('fetchReactionsForMessage error:', err)
    }
  },

  handleReactionAdded: (messageId, payload) => {
    set(
      produce((draft: ReactionsSlice) => {
        if (!draft.reactionsByMessage[messageId]) {
          draft.reactionsByMessage[messageId] = []
        }
        const existingEmojis = draft.reactionsByMessage[messageId]
        const reactionIdx = existingEmojis.findIndex((r) => r.emoji === payload.emoji)
        if (reactionIdx >= 0) {
          // Already have this emoji in the list
          existingEmojis[reactionIdx].count += 1
          existingEmojis[reactionIdx].users.push(payload.user_id)
        } else {
          // Insert new
          existingEmojis.push({ emoji: payload.emoji, count: 1, users: [payload.user_id] })
        }
      })
    )
  },

  handleReactionRemoved: (messageId, payload) => {
    set(
      produce((draft: ReactionsSlice) => {
        const existingEmojis = draft.reactionsByMessage[messageId]
        if (!existingEmojis) return
        const reactionIdx = existingEmojis.findIndex((r) => r.emoji === payload.emoji)
        if (reactionIdx >= 0) {
          const r = existingEmojis[reactionIdx]
          // Remove the user from that reaction’s users
          r.users = r.users.filter((u) => u !== payload.user_id)
          r.count = r.users.length
          // If count is now 0, remove the entire reaction
          if (r.count <= 0) {
            existingEmojis.splice(reactionIdx, 1)
          }
        }
      })
    )
  }
})

// -------------------------------------------------------------------
// 3) Create Store
// -------------------------------------------------------------------
export const useAppStore = create<AppStore>()(
  devtools((set, get) => ({
    ...createAuthSlice(set, get),
    ...createPresenceSlice(set),
    ...createChannelsSlice(set, get),
    ...createChannelMemberSlice(set, get),
    ...createMessagesSlice(set, get),
    ...createReactionsSlice(set, get)
  }))
) 