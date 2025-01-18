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
  tempToken: string | null
  is2FARequired: boolean
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

// Types for the auth slice
interface AuthState {
  accessToken: string | null
  isAuthenticated: boolean
  userId: number | null
  tempToken: string | null
  is2FARequired: boolean
}

interface LoginCredentials {
  email: string
  password: string
}

interface TOTPVerification {
  totp_code: string
}

// AUTH SLICE
const createAuthSlice = (set: any, get: any): AuthSlice => ({
  // State
  accessToken: null,
  isAuthenticated: false,
  userId: null,
  tempToken: null,
  is2FARequired: false,

  // Actions
  login: async ({ email, password }: LoginCredentials) => {
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail?.message || 'Failed to log in')
      }

      const data = await response.json()

      // If we get a temp_token, 2FA is required
      if (data.temp_token) {
        set((state: AuthState) => ({
          ...state,
          tempToken: data.temp_token,
          is2FARequired: true
        }))
        return { requires2FA: true }
      }

      // Direct login (test mode)
      if (data.access_token) {
        set((state: AuthState) => ({
          ...state,
          accessToken: data.access_token,
          isAuthenticated: true,
          userId: data.user_id,
          tempToken: null,
          is2FARequired: false
        }))
        
        if (data.refresh_token) {
          localStorage.setItem('refresh_token', data.refresh_token)
        }
      }

      return { requires2FA: false }
    } catch (err) {
      console.error('Login error:', err)
      throw err
    }
  },

  verify2FA: async ({ totp_code }: TOTPVerification) => {
    try {
      const { tempToken } = get()
      if (!tempToken) throw new Error('No temporary token available')

      const response = await fetch('/api/auth/verify-2fa', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${tempToken}`
        },
        body: JSON.stringify({ totp_code })
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail?.message || 'Failed to verify 2FA')
      }

      const data = await response.json()

      set((state: AuthState) => ({
        ...state,
        accessToken: data.access_token,
        isAuthenticated: true,
        tempToken: null,
        is2FARequired: false
      }))

      if (data.refresh_token) {
        localStorage.setItem('refresh_token', data.refresh_token)
      }
    } catch (err) {
      console.error('2FA verification error:', err)
      throw err
    }
  },

  logout: () => {
    set((state: AuthState) => ({
      ...state,
      accessToken: null,
      isAuthenticated: false,
      userId: null,
      tempToken: null,
      is2FARequired: false
    }))
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

      if (!response.ok) throw new Error('Token refresh failed')
      
      const data = await response.json()

      set((state: AuthState) => ({
        ...state,
        accessToken: data.access_token,
        isAuthenticated: true
      }))

      if (data.refresh_token) {
        localStorage.setItem('refresh_token', data.refresh_token)
      }
    } catch (err) {
      console.error('Token refresh error:', err)
      get().logout()
    }
  },

  verifyToken: async () => {
    try {
      const { accessToken } = get()
      if (!accessToken) throw new Error('No access token')

      const response = await fetch('/api/auth/verify', {
        headers: { 'Authorization': `Bearer ${accessToken}` }
      })

      if (!response.ok) throw new Error('Token verification failed')
      
      const data = await response.json()
      
      if (data.valid) {
        set((state: AuthState) => ({
          ...state,
          userId: data.user_id,
          isAuthenticated: true
        }))
        return true
      }
      return false
    } catch (err) {
      console.error('Token verification error:', err)
      get().logout()
      return false
    }
  }
})

// Types for the presence slice
interface PresenceState {
  onlineUsers: Record<number, boolean>
  isInitialized: boolean
}

interface PresenceUpdate {
  user_id: number
  status: 'online' | 'offline'
}

interface BulkPresenceUpdate {
  online_users: number[]
}

// PRESENCE SLICE
const createPresenceSlice = (set: any, get: any): PresenceSlice => ({
  // State
  onlineUsers: {},
  isInitialized: false,

  // Actions
  updatePresence: (userId: number, online: boolean) => {
    set(
      produce((draft: PresenceState) => {
        if (online) {
          draft.onlineUsers[userId] = true
        } else {
          delete draft.onlineUsers[userId]
        }
      })
    )
  },

  handlePresenceEvent: (data: PresenceUpdate | BulkPresenceUpdate) => {
    set(
      produce((draft: PresenceState) => {
        // Handle bulk presence update (initial presence data)
        if ('online_users' in data) {
          // Clear existing presence data
          draft.onlineUsers = {}
          // Set all online users
          data.online_users.forEach(userId => {
            draft.onlineUsers[userId] = true
          })
          draft.isInitialized = true
        }
        // Handle individual presence update
        else if ('user_id' in data) {
          if (data.status === 'online') {
            draft.onlineUsers[data.user_id] = true
          } else {
            delete draft.onlineUsers[data.user_id]
          }
        }
      })
    )
  },

  resetPresence: () => {
    set(
      produce((draft: PresenceState) => {
        draft.onlineUsers = {}
        draft.isInitialized = false
      })
    )
  },

  isUserOnline: (userId: number): boolean => {
    return !!get().onlineUsers[userId]
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
    try {
      const accessToken = get().accessToken
      if (!accessToken) return
      const resp = await fetch('/api/channels', {
        headers: { Authorization: `Bearer ${accessToken}` }
      })
      if (!resp.ok) throw new Error('Failed to refresh channels')
      const data: Channel[] = await resp.json()
      set((store: ChannelsSlice) => {
        // Replace channels entirely with fresh data
        const newChannels = data.reduce((map, ch) => {
          map[ch.channel_id] = ch
          return map
        }, {} as Record<number, Channel>)
        return { channels: newChannels }
      })
    } catch (err) {
      console.error('refreshChannels error:', err)
    }
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
    const { userId, channels, refreshChannels } = get()
    // If the joinedUserId is the current user, and store doesn’t have the channel
    // or wants to do naive refresh, call refreshChannels
    if (joinedUserId === userId && !channels[channelId]) {
      refreshChannels()
    }
  },

  handleLeaveEvent: (channelId, leftUserId) => {
    const { userId, channels, refreshChannels } = get()
    if (leftUserId === userId && channels[channelId]) {
      refreshChannels()
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
      const data: Member[] = await resp.json()
      set((store: ChannelMemberSlice) => {
        return {
          membersByChannel: {
            ...store.membersByChannel,
            [channelId]: data
          }
        }
      })
    } catch (err) {
      console.error('fetchChannelMembers error:', err)
    }
  },

  clearChannelMembers: (channelId: number) => {
    set((store: ChannelMemberSlice) => {
      const updated = { ...store.membersByChannel }
      delete updated[channelId]
      return { membersByChannel: updated }
    })
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
    ...createPresenceSlice(set, get),
    ...createChannelsSlice(set, get),
    ...createChannelMemberSlice(set, get),
    ...createMessagesSlice(set, get),
    ...createReactionsSlice(set, get)
  }))
) 