/** 角色类型定义。 */

export interface Character {
  id: string;
  projectId: string;
  name: string;
  description: string;
  imageUrl: string | null;
  isFavorited: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CharacterListItem {
  id: string;
  projectId: string;
  name: string;
  imageUrl: string | null;
  tokenCount: number;
  isFavorited: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CharacterCreate {
  name: string;
  description?: string;
  image?: File | null;
}

export interface CharacterUpdate {
  name?: string;
  description?: string;
  image?: File | null;
  isFavorited?: boolean;
}

export interface CharacterListResponse {
  items: CharacterListItem[];
  total: number;
}

export interface CharacterSearchMatch {
  lineNumber: number;
  lineText: string;
}

export interface CharacterSearchResult {
  characterId: string;
  characterName: string;
  matches: CharacterSearchMatch[];
}

export interface CharacterSearchResponse {
  results: CharacterSearchResult[];
  totalCharacters: number;
  totalMatches: number;
}

export interface CharacterRelationship {
  id: string;
  projectId: string;
  fromCharacterId: string;
  toCharacterId: string;
  relationType: string;
  description: string;
  createdAt: string;
  updatedAt: string;
}

export interface CharacterRelationshipListResponse {
  items: CharacterRelationship[];
  total: number;
}

export interface CharacterAppearance {
  characterId: string;
  name: string;
  chapterCount: number;
  totalChapters: number;
  coverage: number;
  firstChapterId: string | null;
  firstChapterTitle: string | null;
  lastChapterId: string | null;
  lastChapterTitle: string | null;
}

export interface CharacterAppearanceListResponse {
  items: CharacterAppearance[];
}
