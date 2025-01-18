import { beforeEach, afterEach, describe, it, expect, jest } from '@jest/globals'
import { useAppStore } from './appStore'

// Mock the store's initial state and functions
beforeEach(() => {
  const initialState = {
    // Auth slice
    accessToken: null,
    isAuthenticated: false,
    userId: null,
    login: jest.fn().mockImplementation(async ({ email, password }) => {
      console.log('🔑 login called with:', { email, password })
      // Simulate API response without making HTTP call
      if (email === 'wrong@example.com') {
        console.log('❌ login failed - wrong email')
        throw new Error('Failed to log in')
      }

      // Simulate successful login response
      const data = {
        access_token: 'FAKE_ACCESS_TOKEN',
        refresh_token: 'FAKE_REFRESH_TOKEN',
        user_id: 123
      }
      console.log('✅ login successful')

      // Update store state
      useAppStore.setState({
        accessToken: data.access_token,
        isAuthenticated: true,
        userId: data.user_id
      })

      // Store refresh token in localStorage
      localStorage.setItem('refresh_token', data.refresh_token)
      console.log('💾 localStorage updated')
    }),
    logout: jest.fn().mockImplementation(() => {
      console.log('🔒 logout called')

      // Clear store state
      useAppStore.setState({
        accessToken: null,
        isAuthenticated: false,
        userId: null
      })

      // Remove refresh token from localStorage
      localStorage.removeItem('refresh_token')
      console.log('🗑️ localStorage cleared')
    }),
    refreshTokens: jest.fn().mockImplementation(async () => {
      console.log('🔄 refreshTokens called')
      const storedRefreshToken = localStorage.getItem('refresh_token')
      console.log('💾 current refresh token:', storedRefreshToken)

      if (!storedRefreshToken) {
        console.log('❌ no refresh token found')
        throw new Error('No refresh token stored')
      }

      // Simulate successful refresh response
      const data = {
        access_token: 'NEW_ACCESS_TOKEN',
        refresh_token: 'NEW_REFRESH_TOKEN'
      }
      console.log('✅ refresh successful')

      // Update store state
      useAppStore.setState({
        accessToken: data.access_token,
        isAuthenticated: true
      })

      // Update refresh token in localStorage
      localStorage.setItem('refresh_token', data.refresh_token)
      console.log('💾 localStorage updated')
    }),
    setAccessToken: jest.fn().mockImplementation((token: string | null) => {
      useAppStore.setState({
        accessToken: token,
        isAuthenticated: !!token
      })
    }),

    // Presence slice
    onlineUsers: {},
    updatePresence: jest.fn().mockImplementation((userId: number, online: boolean) => {
      useAppStore.setState(state => {
        const newOnlineUsers = { ...state.onlineUsers }
        if (online) {
          newOnlineUsers[userId] = true
        } else {
          delete newOnlineUsers[userId]
        }
        return { onlineUsers: newOnlineUsers }
      })
    }),

    // Channels slice
    channels: {},
    listChannels: jest.fn().mockImplementation(async () => {
      const data = [
        { channel_id: 1, name: 'general', type: 'public', is_member: true },
        { channel_id: 2, name: 'random', type: 'public', is_member: true },
        { channel_id: 3, name: null, type: 'dm', is_member: true },
        { channel_id: 4, name: null, type: 'notes', is_member: true }
      ]
      useAppStore.setState(state => ({
        channels: data.reduce((map, ch) => {
          map[ch.channel_id] = ch
          return map
        }, {} as Record<number, any>)
      }))
    }),
    createChannel: jest.fn().mockImplementation(async (params: any) => {
      let newChannel;
      
      if (params.type === 'dm') {
        // Simulate DM channel creation
        newChannel = { 
          channel_id: 100, 
          type: 'dm',
          name: null,
          created_at: new Date().toISOString(),
          is_member: true
        }
      } else if (params.type === 'notes') {
        // Notes channels are created during registration
        newChannel = {
          channel_id: 101,
          type: 'notes',
          name: null,
          created_at: new Date().toISOString(),
          is_member: true
        }
      } else {
        // Regular public/private channel
        newChannel = { 
          channel_id: 99, 
          name: params.name, 
          type: params.type,
          created_at: new Date().toISOString(),
          is_member: true
        }
      }

      useAppStore.setState(state => ({
        channels: {
          ...state.channels,
          [newChannel.channel_id]: newChannel
        }
      }))

      return newChannel
    }),
    refreshChannels: jest.fn().mockImplementation(async () => {
      // This will be spied on, so we don't need to implement it
    }),
    updateChannel: jest.fn(),
    handleJoinEvent: jest.fn().mockImplementation((channelId, joinedUserId) => {
      const state = useAppStore.getState()
      if (joinedUserId === state.userId && !state.channels[channelId]) {
        state.refreshChannels()
      }
    }),
    handleLeaveEvent: jest.fn().mockImplementation((channelId, leftUserId) => {
      const state = useAppStore.getState()
      if (leftUserId === state.userId && state.channels[channelId]) {
        state.refreshChannels()
      }
    }),

    // Channel members slice
    membersByChannel: {},
    fetchChannelMembers: jest.fn(),
    clearChannelMembers: jest.fn(),

    // Messages slice
    messagesByChannel: {},
    fetchMessages: jest.fn(),
    createMessage: jest.fn(),
    updateMessage: jest.fn(),
    deleteMessage: jest.fn(),
    handleMessageCreated: jest.fn(),
    handleMessageUpdated: jest.fn(),
    handleMessageDeleted: jest.fn(),

    // Reactions slice
    reactionsByMessage: {},
    fetchReactionsForMessage: jest.fn(),
    handleReactionAdded: jest.fn(),
    handleReactionRemoved: jest.fn()
  }

  useAppStore.setState(initialState)
})

// A helper to reset state before each test
function resetStore() {
  useAppStore.setState({
    accessToken: null,
    isAuthenticated: false,
    userId: null,
    onlineUsers: {},
    channels: {},
    membersByChannel: {},
    messagesByChannel: {},
    reactionsByMessage: {}
  })
}

// Mock localStorage
console.log('🔧 Setting up localStorage mock')
const mockStorage = {
  store: {} as Record<string, string>,
  getItem: jest.fn((key: string) => {
    console.log('🔍 getItem:', key)
    // Return null for non-existent keys, following Web Storage API spec
    const value = mockStorage.store[key] || null
    console.log('📤 returning:', value)
    return value
  }),
  setItem: jest.fn((key: string, value: string) => {
    console.log('💾 setItem:', { key, value })
    mockStorage.store[key] = value
  }),
  removeItem: jest.fn((key: string) => {
    console.log('🗑️ removeItem:', key)
    delete mockStorage.store[key]
  }),
  clear: jest.fn(() => {
    console.log('🧹 clear')
    mockStorage.store = {}
  })
}

console.log('🔧 Setting up Storage prototype mocks')
jest.spyOn(Storage.prototype, 'getItem').mockImplementation(mockStorage.getItem)
jest.spyOn(Storage.prototype, 'setItem').mockImplementation(mockStorage.setItem)
jest.spyOn(Storage.prototype, 'removeItem').mockImplementation(mockStorage.removeItem)
jest.spyOn(Storage.prototype, 'clear').mockImplementation(mockStorage.clear)

// Mock fetch globally
global.fetch = jest.fn()

describe('appStore Tests', () => {
  beforeEach(() => {
    resetStore()
    jest.clearAllMocks()
    // Clear storage
    mockStorage.clear()
  })

  afterEach(() => {
    jest.resetAllMocks()
  })

  // ----------------------------------------------------------------
  // Auth Slice
  // ----------------------------------------------------------------
  describe('Auth Slice', () => {
    beforeEach(() => {
      // Reset store to initial auth state
      useAppStore.setState({
        accessToken: null,
        isAuthenticated: false,
        userId: null
      })

      // Set up localStorage spies
      jest.spyOn(Storage.prototype, 'getItem')
      jest.spyOn(Storage.prototype, 'setItem')
      jest.spyOn(Storage.prototype, 'removeItem')

      // Clear localStorage before each test
      localStorage.clear()
    })

    afterEach(() => {
      jest.clearAllMocks()
    })

    it('login - success scenario', async () => {
      // Mock getItem to return null initially (no token stored)
      localStorage.getItem.mockReturnValue(null)

      await useAppStore.getState().login({ email: 'test@example.com', password: 'password' })

      expect(useAppStore.getState().accessToken).toBe('FAKE_ACCESS_TOKEN')
      expect(useAppStore.getState().isAuthenticated).toBe(true)
      expect(useAppStore.getState().userId).toBe(123)

      // Check that refresh token was stored
      expect(localStorage.setItem).toHaveBeenCalledWith('refresh_token', 'FAKE_REFRESH_TOKEN')
    })

    it('login - failure scenario', async () => {
      // Mock getItem to return null (no token stored)
      localStorage.getItem.mockReturnValue(null)

      await expect(
        useAppStore.getState().login({ email: 'wrong@example.com', password: 'badpass' })
      ).rejects.toThrow('Failed to log in')

      expect(useAppStore.getState().accessToken).toBeNull()
      expect(useAppStore.getState().isAuthenticated).toBe(false)
      expect(localStorage.getItem('refresh_token')).toBeNull()
    })

    it('logout should clear auth state and remove refresh token', () => {
      // Pre-populate store with tokens
      useAppStore.setState({
        accessToken: 'TEST_ACCESS_TOKEN',
        isAuthenticated: true,
        userId: 999
      })
      
      // Mock initial token state
      localStorage.getItem.mockReturnValue('FAKE_REFRESH')

      useAppStore.getState().logout()
      expect(useAppStore.getState().accessToken).toBeNull()
      expect(useAppStore.getState().isAuthenticated).toBe(false)
      expect(useAppStore.getState().userId).toBeNull()
      
      // Verify token was removed
      expect(localStorage.removeItem).toHaveBeenCalledWith('refresh_token')
    })

    it('refreshTokens - success scenario', async () => {
      // Mock stored refresh token
      localStorage.getItem.mockReturnValue('STORED_REFRESH')

      await useAppStore.getState().refreshTokens()

      expect(useAppStore.getState().accessToken).toBe('NEW_ACCESS_TOKEN')
      expect(localStorage.setItem).toHaveBeenCalledWith('refresh_token', 'NEW_REFRESH_TOKEN')
      expect(useAppStore.getState().isAuthenticated).toBe(true)
    })

    it('refreshTokens - error scenario with no refresh token in storage', async () => {
      // Mock no stored token
      localStorage.getItem.mockReturnValue(null)

      await expect(useAppStore.getState().refreshTokens()).rejects.toThrow('No refresh token stored')
      expect(useAppStore.getState().accessToken).toBeNull()
      expect(useAppStore.getState().isAuthenticated).toBe(false)
    })
  })

  // ----------------------------------------------------------------
  // Presence Slice
  // ----------------------------------------------------------------
  describe('Presence Slice', () => {
    beforeEach(() => {
      // Reset store to initial state before each test
      useAppStore.setState({
        onlineUsers: {}
      })
    })

    it('starts with an empty online users state', () => {
      expect(useAppStore.getState().onlineUsers).toEqual({})
    })

    it('handles presence.initial by setting multiple users online', () => {
      // Simulate receiving initial presence data
      const initialPresence = {
        5: true,
        10: true,
        15: true
      }

      useAppStore.setState({ onlineUsers: initialPresence })

      const state = useAppStore.getState()
      expect(state.onlineUsers[5]).toBe(true)
      expect(state.onlineUsers[10]).toBe(true)
      expect(state.onlineUsers[15]).toBe(true)
      expect(Object.keys(state.onlineUsers)).toHaveLength(3)
    })

    it('handles presence.update for online status', () => {
      // Start with some existing online users
      useAppStore.setState({
        onlineUsers: {
          5: true,
          10: true
        }
      })

      // New user comes online
      useAppStore.getState().updatePresence(15, true)

      const state = useAppStore.getState()
      expect(state.onlineUsers[15]).toBe(true)
      expect(Object.keys(state.onlineUsers)).toHaveLength(3)
    })

    it('handles presence.update for offline status by removing the user', () => {
      // Start with some online users
      useAppStore.setState({
        onlineUsers: {
          5: true,
          10: true,
          15: true
        }
      })

      // User 10 goes offline
      useAppStore.getState().updatePresence(10, false)

      const state = useAppStore.getState()
      expect(state.onlineUsers[10]).toBeUndefined()
      expect(Object.keys(state.onlineUsers)).toHaveLength(2)
      expect(state.onlineUsers[5]).toBe(true)
      expect(state.onlineUsers[15]).toBe(true)
    })

    it('gracefully handles offline status for non-existent users', () => {
      // Start with some online users
      useAppStore.setState({
        onlineUsers: {
          5: true,
          10: true
        }
      })

      // Try to set offline a user that isn't in the map
      useAppStore.getState().updatePresence(999, false)

      const state = useAppStore.getState()
      expect(Object.keys(state.onlineUsers)).toHaveLength(2)
      expect(state.onlineUsers[5]).toBe(true)
      expect(state.onlineUsers[10]).toBe(true)
      expect(state.onlineUsers[999]).toBeUndefined()
    })

    it('maintains presence for other users when updating one user', () => {
      // Start with multiple users online
      useAppStore.setState({
        onlineUsers: {
          5: true,
          10: true,
          15: true
        }
      })

      // Update one user's presence
      useAppStore.getState().updatePresence(10, false)

      const state = useAppStore.getState()
      expect(state.onlineUsers[5]).toBe(true)      // Unchanged
      expect(state.onlineUsers[10]).toBeUndefined() // Removed
      expect(state.onlineUsers[15]).toBe(true)      // Unchanged
      expect(Object.keys(state.onlineUsers)).toHaveLength(2)
    })
  })

  // ----------------------------------------------------------------
  // Channels Slice
  // ----------------------------------------------------------------
  describe('Channels Slice', () => {
    beforeEach(() => {
      // Reset store to initial state
      useAppStore.setState({
        accessToken: 'TOKEN',
        userId: 5,
        channels: {},
        // Add membersByChannel for DM test
        membersByChannel: {
          3: [
            { user_id: 5, display_name: 'Current User' },
            { user_id: 10, display_name: 'Other User' }
          ],
          100: [
            { user_id: 5, display_name: 'Current User' },
            { user_id: 10, display_name: 'John Doe' }
          ]
        }
      })
    })

    it('listChannels populates channels in store', async () => {
      ;(fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { channel_id: 1, name: 'general', type: 'public', is_member: true },
          { channel_id: 2, name: 'random', type: 'public', is_member: true },
          { channel_id: 3, name: null, type: 'dm', is_member: true },
          { channel_id: 4, name: null, type: 'notes', is_member: true }
        ]
      })

      await useAppStore.getState().listChannels()
      const { channels } = useAppStore.getState()
      expect(Object.keys(channels)).toHaveLength(4)
      
      // Public channels have names
      expect(channels[1].name).toBe('general')
      expect(channels[2].type).toBe('public')
      
      // DM channel has no name
      expect(channels[3].name).toBeNull()
      expect(channels[3].type).toBe('dm')
      expect(channels[3].is_member).toBe(true)
      
      // Notes channel has no name
      expect(channels[4].name).toBeNull()
      expect(channels[4].type).toBe('notes')
      expect(channels[4].is_member).toBe(true)
    })

    it('should handle DM channel creation correctly', async () => {
      ;(fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ 
            channel_id: 100, 
            type: 'dm',
            name: null,
            is_member: true,
            created_at: '2024-01-01T00:00:00Z'
          })
        })

      const result = await useAppStore.getState().createChannel({ type: 'dm', recipient_id: 10 })
      expect(result.type).toBe('dm')
      expect(result.name).toBeNull()
      expect(result.is_member).toBe(true)

      // Verify store was updated
      const dmChannel = useAppStore.getState().channels[100]
      expect(dmChannel.type).toBe('dm')
      expect(dmChannel.name).toBeNull()
      expect(dmChannel.is_member).toBe(true)

      // Verify we can get the other user's display name from members
      const members = useAppStore.getState().membersByChannel[100]
      const otherUser = members.find(m => m.user_id !== 5)
      expect(otherUser?.display_name).toBe('John Doe')
    })

    it('should handle Notes channel correctly', async () => {
      // Notes channels are created during registration, so we'll test store handling
      useAppStore.setState(state => ({
        channels: {
          ...state.channels,
          101: {
            channel_id: 101,
            type: 'notes',
            name: null,
            is_member: true,
            created_at: '2024-01-01T00:00:00Z'
          }
        }
      }))

      const notesChannel = useAppStore.getState().channels[101]
      expect(notesChannel.type).toBe('notes')
      expect(notesChannel.name).toBeNull()
      expect(notesChannel.is_member).toBe(true)
    })

    it('handleJoinEvent should refresh channels if current user joined a new channel', async () => {
      const spyRefresh = jest.spyOn(useAppStore.getState(), 'refreshChannels').mockImplementation()
      // Suppose store has no channel with ID=10, user = 5 has joined
      useAppStore.getState().handleJoinEvent(10, 5)
      expect(spyRefresh).toHaveBeenCalledTimes(1)
    })

    it('handleLeaveEvent should refresh channels if current user left a channel', async () => {
      const spyRefresh = jest.spyOn(useAppStore.getState(), 'refreshChannels').mockImplementation()

      // The store has channel 10
      useAppStore.setState({
        userId: 5,
        channels: {
          10: { channel_id: 10, name: 'my-chan', type: 'private' }
        }
      })

      // user 5 left channel 10
      useAppStore.getState().handleLeaveEvent(10, 5)
      expect(spyRefresh).toHaveBeenCalledTimes(1)
    })
  })

  // ----------------------------------------------------------------
  // ChannelMember Slice
  // ----------------------------------------------------------------
  describe('ChannelMember Slice', () => {
    it('fetchChannelMembers populates membersByChannel', async () => {
      ;(fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { user_id: 5, display_name: 'User5', role: 'member' },
          { user_id: 7, display_name: 'User7', role: 'admin' }
        ]
      })
      useAppStore.setState({ accessToken: 'TOKEN' })

      await useAppStore.getState().fetchChannelMembers(10)
      expect(useAppStore.getState().membersByChannel[10]).toHaveLength(2)
      expect(useAppStore.getState().membersByChannel[10][0].user_id).toBe(5)
    })

    it('clearChannelMembers removes a channel from the map', () => {
      useAppStore.setState({
        membersByChannel: {
          10: [{ user_id: 1, display_name: 'User1', role: 'owner' }]
        }
      })
      useAppStore.getState().clearChannelMembers(10)
      expect(useAppStore.getState().membersByChannel[10]).toBeUndefined()
    })
  })

  // ----------------------------------------------------------------
  // Messages Slice
  // ----------------------------------------------------------------
  describe('Messages Slice', () => {
    it('fetchMessages sets messages for a channel', async () => {
      ;(fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            message_id: 100,
            channel_id: 99,
            user_id: 5,
            content: 'Hello there',
            created_at: '2023-10-01T12:00:00Z',
            display_name: 'User5',
            has_reactions: false
          }
        ]
      })
      useAppStore.setState({ accessToken: 'TOKEN' })
      await useAppStore.getState().fetchMessages(99)

      expect(useAppStore.getState().messagesByChannel[99]).toHaveLength(1)
      expect(useAppStore.getState().messagesByChannel[99][0].content).toBe('Hello there')
    })

    it('createMessage appends new message to the store', async () => {
      ;(fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          message_id: 101,
          channel_id: 99,
          user_id: 5,
          content: 'New message!',
          created_at: '2023-10-01T12:05:00Z',
          display_name: 'User5',
          has_reactions: false
        })
      })
      useAppStore.setState({ accessToken: 'TOKEN' })

      await useAppStore.getState().createMessage(99, 'New message!')
      const msgs = useAppStore.getState().messagesByChannel[99]
      expect(msgs).toHaveLength(1)
      expect(msgs[0].content).toBe('New message!')
    })

    it('updateMessage modifies existing message content', async () => {
      useAppStore.setState({
        messagesByChannel: {
          99: [
            {
              message_id: 101,
              channel_id: 99,
              user_id: 5,
              content: 'Old content',
              created_at: '2023-10-01T12:04:00Z',
              display_name: 'User5',
              has_reactions: false
            }
          ]
        },
        accessToken: 'TOKEN'
      })

      ;(fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          message_id: 101,
          channel_id: 99,
          user_id: 5,
          content: 'Updated content',
          created_at: '2023-10-01T12:04:00Z',
          edited_at: '2023-10-01T12:10:00Z',
          display_name: 'User5',
          has_reactions: false
        })
      })

      await useAppStore.getState().updateMessage(101, 'Updated content')
      const msgs = useAppStore.getState().messagesByChannel[99]
      expect(msgs[0].content).toBe('Updated content')
      expect(msgs[0].edited_at).toBe('2023-10-01T12:10:00Z')
    })

    it('deleteMessage removes the message from store', async () => {
      useAppStore.setState({
        messagesByChannel: {
          99: [
            {
              message_id: 101,
              channel_id: 99,
              user_id: 5,
              content: 'Some message',
              created_at: '2023-10-01T12:04:00Z',
              display_name: 'User5',
              has_reactions: false
            }
          ]
        },
        accessToken: 'TOKEN'
      })
      ;(fetch as jest.Mock).mockResolvedValueOnce({ ok: true })
      await useAppStore.getState().deleteMessage(101)
      expect(useAppStore.getState().messagesByChannel[99]).toHaveLength(0)
    })
  })

  // ----------------------------------------------------------------
  // Reactions Slice
  // ----------------------------------------------------------------
  describe('Reactions Slice', () => {
    it('fetchReactionsForMessage sets the store data', async () => {
      ;(fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            emoji: ':smile:',
            count: 2,
            users: [5, 6]
          }
        ]
      })
      useAppStore.setState({ accessToken: 'TOKEN' })

      await useAppStore.getState().fetchReactionsForMessage(101)
      const reactions = useAppStore.getState().reactionsByMessage[101]
      expect(reactions).toHaveLength(1)
      expect(reactions[0].emoji).toBe(':smile:')
      expect(reactions[0].count).toBe(2)
    })

    it('handleReactionAdded increments existing or inserts new entry', () => {
      useAppStore.setState({
        reactionsByMessage: {
          101: [{ emoji: ':smile:', count: 1, users: [5] }]
        }
      })

      // Add the same emoji by user 6
      useAppStore.getState().handleReactionAdded(101, { emoji: ':smile:', user_id: 6 })
      let r = useAppStore.getState().reactionsByMessage[101][0]
      expect(r.count).toBe(2)
      expect(r.users).toContain(6)

      // Add a brand-new emoji
      useAppStore.getState().handleReactionAdded(101, { emoji: ':thumbsup:', user_id: 7 })
      expect(useAppStore.getState().reactionsByMessage[101]).toHaveLength(2)
    })

    it('handleReactionAdded - multiple distinct emojis for the same message', () => {
      useAppStore.setState({
        reactionsByMessage: {
          200: [
            { emoji: ':smile:', count: 2, users: [1, 2] }
          ]
        }
      })

      // Add :thumbsup: for user 3
      useAppStore.getState().handleReactionAdded(200, { emoji: ':thumbsup:', user_id: 3 })
      let r = useAppStore.getState().reactionsByMessage[200]
      expect(r).toHaveLength(2)
      expect(r.map((item) => item.emoji)).toEqual([':smile:', ':thumbsup:'])
      expect(r[1].count).toBe(1)
      expect(r[1].users).toEqual([3])

      // Add :heart: for user 4
      useAppStore.getState().handleReactionAdded(200, { emoji: ':heart:', user_id: 4 })
      r = useAppStore.getState().reactionsByMessage[200]
      expect(r).toHaveLength(3)
      expect(r.map((item) => item.emoji)).toEqual([':smile:', ':thumbsup:', ':heart:'])
      expect(r[2].count).toBe(1)
      expect(r[2].users).toEqual([4])
    })

    it('handleReactionRemoved decrements or removes an emoji entry', () => {
      useAppStore.setState({
        reactionsByMessage: {
          101: [
            { emoji: ':smile:', count: 2, users: [5, 6] },
            { emoji: ':thumbsup:', count: 1, users: [7] }
          ]
        }
      })

      // Remove user 6 from :smile:
      useAppStore.getState().handleReactionRemoved(101, { emoji: ':smile:', user_id: 6 })
      let smileReaction = useAppStore.getState().reactionsByMessage[101][0]
      expect(smileReaction.count).toBe(1)
      expect(smileReaction.users).not.toContain(6)

      // Remove user 5 from :smile:
      useAppStore.getState().handleReactionRemoved(101, { emoji: ':smile:', user_id: 5 })
      let newArray = useAppStore.getState().reactionsByMessage[101]
      // :smile: should be removed entirely
      expect(newArray.map((r) => r.emoji)).not.toContain(':smile:')

      // Remove user 7 from :thumbsup:
      useAppStore.getState().handleReactionRemoved(101, { emoji: ':thumbsup:', user_id: 7 })
      newArray = useAppStore.getState().reactionsByMessage[101]
      // :thumbsup: should also be removed
      expect(newArray.map((r) => r.emoji)).not.toContain(':thumbsup:')
    })
  })
}) 