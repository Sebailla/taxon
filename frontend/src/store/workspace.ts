import { create } from "zustand";

import {
  createSpeciesFolder,
  deleteExplored,
  deleteLinkVisited,
  fetchExploredList,
  fetchLinkVisited,
  fetchSpeciesFolder,
  postExplored,
  postLinkVisited,
  speciesKey,
} from "../api";

export interface ActiveLink {
  speciesKey: string;
  source: string;
  url: string;
}

export interface WorkspaceState {
  explored: Set<string>;
  folders: Map<string, string>;
  visitedLinks: Map<string, Set<string>>;
  activeLink: ActiveLink | null;
  loadExploredList: () => Promise<void>;
  toggleExplored: (genus: string, epithet: string) => Promise<void>;
  loadFolder: (genus: string, epithet: string) => Promise<void>;
  createFolder: (genus: string, epithet: string) => Promise<void>;
  loadVisited: (genus: string, epithet: string) => Promise<void>;
  toggleVisited: (genus: string, epithet: string, source: string) => Promise<void>;
  setActiveLink: (link: ActiveLink | null) => void;
  clear: () => void;
}

const emptyState = () => ({
  explored: new Set<string>(),
  folders: new Map<string, string>(),
  visitedLinks: new Map<string, Set<string>>(),
  activeLink: null,
});

export const useWorkspace = create<WorkspaceState>((set, get) => ({
  ...emptyState(),
  loadExploredList: async () => {
    const result = await fetchExploredList();
    if (result.status === "ok") set({ explored: new Set(result.data.species.map((row) => speciesKey(row.genus, row.epithet))) });
  },
  toggleExplored: async (genus, epithet) => {
    const key = speciesKey(genus, epithet);
    const enabled = get().explored.has(key);
    const result = enabled ? await deleteExplored(genus, epithet) : await postExplored(genus, epithet);
    if (result.status === "ok") set((state) => {
      const explored = new Set(state.explored);
      enabled ? explored.delete(key) : explored.add(key);
      return { explored };
    });
  },
  loadFolder: async (genus, epithet) => {
    const result = await fetchSpeciesFolder(genus, epithet);
    if (result.status === "ok") set((state) => ({ folders: new Map(state.folders).set(speciesKey(genus, epithet), result.data.path) }));
  },
  createFolder: async (genus, epithet) => {
    const result = await createSpeciesFolder(genus, epithet);
    if (result.status === "ok") set((state) => ({ folders: new Map(state.folders).set(speciesKey(genus, epithet), result.data.path) }));
  },
  loadVisited: async (genus, epithet) => {
    const result = await fetchLinkVisited(genus, epithet);
    if (result.status === "ok") set((state) => ({ visitedLinks: new Map(state.visitedLinks).set(speciesKey(genus, epithet), new Set(result.data.sources.map((row) => row.source))) }));
  },
  toggleVisited: async (genus, epithet, source) => {
    const key = speciesKey(genus, epithet);
    const enabled = get().visitedLinks.get(key)?.has(source) ?? false;
    const result = enabled ? await deleteLinkVisited(genus, epithet, source) : await postLinkVisited(genus, epithet, source);
    if (result.status === "ok") set((state) => {
      const visitedLinks = new Map(state.visitedLinks);
      const sources = new Set(visitedLinks.get(key));
      enabled ? sources.delete(source) : sources.add(source);
      visitedLinks.set(key, sources);
      return { visitedLinks };
    });
  },
  setActiveLink: (activeLink) => set({ activeLink }),
  clear: () => set(emptyState()),
}));
