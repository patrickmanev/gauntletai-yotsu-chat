export type User = {
  name: string;
  avatar: string;
  initials: string;
}

export type ActiveView = {
  type: 'channel' | 'dm';
  data: string | User;
}

export type SidePanel = {
  type: 'thread' | 'profile' | null;
  data: string | User | null;
}

