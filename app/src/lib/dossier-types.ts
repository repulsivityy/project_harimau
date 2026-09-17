export type SwimLaneCategory = 'ingress' | 'execution' | 'decoy' | 'dropped' | 'c2';

export interface MitreTechnique {
  id: string;
  name?: string;
  tactic?: string;
}

export interface SpecialistReportData {
  verdict?: string;
  confidence?: string;
  summary?: string;
  markdown_report?: string;
  mitre_attack?: MitreTechnique[];
  key_findings?: string[];
  analyzed_targets?: Array<string | { id?: string; value?: string }>;
  iocs_extracted?: Array<string | { id?: string; value?: string }>;
}

export interface MalwareSpecialistReport extends SpecialistReportData {
  agent_id?: 'AGENT-01';
}

export interface InfraSpecialistReport extends SpecialistReportData {
  agent_id?: 'AGENT-02';
}

export interface DossierJob {
  job_id: string;
  status?: string;
  ioc: string;
  ioc_type?: string;
  risk_level?: string;
  gti_score?: number | null;
  created_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  confidence?: string;
  attribution?: string;
  campaign?: string;
  mitre_attack?: MitreTechnique[];
  rich_intel?: {
    malicious_stats?: number;
    total_stats?: number;
    gti_description?: string;
    triage_summary?: string;
  };
  specialist_reports?: {
    malware_specialist?: MalwareSpecialistReport;
    malware?: MalwareSpecialistReport;
    infrastructure_specialist?: InfraSpecialistReport;
    infrastructure?: InfraSpecialistReport;
  };
  specialist_results?: {
    malware_specialist?: MalwareSpecialistReport;
    malware?: MalwareSpecialistReport;
    infrastructure_specialist?: InfraSpecialistReport;
    infrastructure?: InfraSpecialistReport;
  };
  metadata?: {
    specialist_results?: {
      malware_specialist?: MalwareSpecialistReport;
      malware?: MalwareSpecialistReport;
      infrastructure_specialist?: InfraSpecialistReport;
      infrastructure?: InfraSpecialistReport;
    };
    error?: string;
    transparency_log?: unknown[];
  };
  transparency_log?: unknown[];
  final_report?: string;
  subtasks?: Array<{
    agent?: string;
    status?: string;
    task?: string;
    timestamp?: string;
  }>;
  graph?: {
    nodes?: unknown[];
    edges?: unknown[];
  };
  investigation_graph?: {
    nodes?: unknown[];
    edges?: unknown[];
  };
}

export interface ParsedDotNode {
  id: string;
  label: string;
  friendlyName?: string;
  rawLabel?: string;
  isRoot?: boolean;
  entityType: string;
  isDecoy?: boolean;
  threatScore?: number;
  verdict?: string;
  isMalicious?: boolean;
}

export interface ParsedDotEdge {
  source: string;
  target: string;
  label: string;
}

export interface ParsedDotGraph {
  nodes: ParsedDotNode[];
  edges: ParsedDotEdge[];
}

export interface SwimLaneStage {
  id: string;
  category: SwimLaneCategory;
  title: string;
  badgeText: string;
  icon: string;
  cardBorder: string;
  headerColor: string;
  numBg: string;
  badgeBg: string;
  itemBadgeStyle: string;
  itemRoleLabel: string;
  nodes: ParsedDotNode[];
}

export interface IocEntry {
  type: string;
  value: string;
  notes: string;
  confidence: string;
}

export interface DossierSection {
  number: number;
  id: string;
  title: string;
  markdownBody: string;
}

export interface ParsedDossierReport {
  preamble: string;
  sections: DossierSection[];
  rawDotCode: string | null;
  parsedDotGraph: ParsedDotGraph;
  appendixIocs: IocEntry[];
  normalizedMarkdown: string;
}

// ============================================================================
// Shared Component Prop Contracts
// ============================================================================

export interface DossierSharedCallbacks {
  onJumpToNode: (nodeId: string) => void;
  onCopyIoc: (value: string) => void;
}

export interface DossierMastheadProps {
  job: DossierJob;
  graphEntityCount: number;
}

export interface SpecialistReportsGridProps extends DossierSharedCallbacks {
  job: DossierJob;
}

export interface DossierCompanionRailProps extends DossierSharedCallbacks {
  job: DossierJob;
  onOpenCanvasTab: () => void;
  onToggleAgentLog?: () => void;
}

export interface AttackFlowSectionProps extends DossierSharedCallbacks {
  job: DossierJob;
  rawDotCode: string | null;
  parsedGraph: ParsedDotGraph;
  swimLanes: SwimLaneStage[];
  onExploreInCanvas?: () => void;
}

export interface TacticalSwimLanesProps extends DossierSharedCallbacks {
  activeStages: SwimLaneStage[];
}

export interface DecoyInsightBannerProps {
  decoyCount: number;
}

export interface AppendixIocTableProps extends DossierSharedCallbacks {
  iocs: IocEntry[];
}
