export interface TavernLorePreview {
  name: string;
  keywords: string[];
  isConstant: boolean;
  isEnabled: boolean;
}

export interface TavernBlockPreview {
  blockId: string;
  name: string;
  contentPreview: string;
  bucket: string;
  reason: string;
  included: boolean;
}

export interface TavernPreview {
  kind: string;
  characterName: string;
  descriptionPreview: string;
  discarded: string[];
  constantCount: number;
  keywordCount: number;
  loreEntries: TavernLorePreview[];
  presetName: string;
  blocks: TavernBlockPreview[];
}

export interface TavernImportResult {
  kind: string;
  characterId: string | null;
  importedEntries: number;
  importedRules: number;
  importedSkills: number;
}
