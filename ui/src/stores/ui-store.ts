import { create } from 'zustand'

interface UIState {
  sidebar: 'expanded' | 'collapsed'
  globalProjectFilter: string | null
  toggleSidebar: () => void
  setGlobalProjectFilter: (id: string | null) => void
}

export const useUIStore = create<UIState>((set) => ({
  sidebar: 'expanded',
  globalProjectFilter: null,
  toggleSidebar: () =>
    set((state) => ({
      sidebar: state.sidebar === 'expanded' ? 'collapsed' : 'expanded',
    })),
  setGlobalProjectFilter: (id) => set({ globalProjectFilter: id }),
}))
