export interface CreationEvidenceReportCreate {
  chapterId: string | null;
  localDate: string;
}

export interface CreationEvidenceReport {
  id: string;
  status: string;
  filename: string;
  chapterId: string | null;
  current: number;
  total: number;
  stage: string | null;
  expiresAt: string | null;
  jsonDownloadUrl: string | null;
  htmlDownloadUrl: string | null;
  errorMessage: string | null;
}
