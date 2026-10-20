import client from './client';
import type { Person, Project, ProjectMembers, ProjectRole, ProjectStatus, TeamCalendar, WeekdayCode } from '../types';

/** プロジェクト（task #187、ADR-0024）。書いたらタスク・マイルストーンも読み直させる（道筋が変わる）。 */
export const PROJECTS_KEY = ['projects'] as const;

export const getProjects = async (): Promise<Project[]> => {
  const { data } = await client.get<Project[]>('/projects');
  return data;
};

export interface ProjectInput {
  name?: string;
  color?: string | null;
  code?: string | null;
  description?: string | null;
  status?: ProjectStatus;
}

export const createProject = async (
  payload: ProjectInput & { name: string; parent_project_id: number | null },
): Promise<Project> => {
  const { data } = await client.post<Project>('/projects', payload);
  return data;
};

export const updateProject = async (id: number, payload: ProjectInput): Promise<Project> => {
  const { data } = await client.put<Project>(`/projects/${id}`, payload);
  return data;
};

/** 親を替える・兄弟の中の位置を変える（position を省くと末尾）。自分の下へは 409。 */
export const moveProject = async (
  id: number, parentProjectId: number | null, position?: number,
): Promise<Project> => {
  const { data } = await client.post<Project>(`/projects/${id}/move`, {
    parent_project_id: parentProjectId, position,
  });
  return data;
};

/** 空のプロジェクトだけ消せる（中身があると 409）。 */
export const deleteProject = async (id: number): Promise<void> => {
  await client.delete(`/projects/${id}`);
};

/** メンバー・担当者に選べる人（WBS に 1 度でもログインした人。ADR-0055）。 */
export const PEOPLE_KEY = ['projects', 'people'] as const;

export const getPeople = async (): Promise<Person[]> => {
  const { data } = await client.get<Person[]>('/projects/people');
  return data;
};

/** その木（いちばん上のプロジェクト）のメンバー。どの段の id で聞いても根の名簿が返る。 */
export const projectMembersKey = (projectId: number) => ['projects', projectId, 'members'] as const;

export const getProjectMembers = async (projectId: number): Promise<ProjectMembers> => {
  const { data } = await client.get<ProjectMembers>(`/projects/${projectId}/members`);
  return data;
};

/** 加える（もう居れば役割を書き換える）。管理者だけ（403）。 */
export const addProjectMember = async (
  projectId: number, userId: number, role: ProjectRole,
): Promise<ProjectMembers> => {
  const { data } = await client.post<ProjectMembers>(`/projects/${projectId}/members`, { user_id: userId, role });
  return data;
};

/** 役割を変える。最後の管理者を下げると 409。 */
export const changeProjectMemberRole = async (
  projectId: number, userId: number, role: ProjectRole,
): Promise<ProjectMembers> => {
  const { data } = await client.put<ProjectMembers>(`/projects/${projectId}/members/${userId}`, { role });
  return data;
};

/** 外す（自分なら抜ける）。最後の管理者は 409。担当は残る。 */
export const removeProjectMember = async (projectId: number, userId: number): Promise<void> => {
  await client.delete(`/projects/${projectId}/members/${userId}`);
};

/** 1 日の工数と従事率（ADR-0058）。管理者は誰のでも、メンバーは自分のだけ（403）。 */
export const changeProjectMemberCapacity = async (
  projectId: number, userId: number, dailyHours: number, engagementPercent: number,
): Promise<ProjectMembers> => {
  const { data } = await client.put<ProjectMembers>(`/projects/${projectId}/members/${userId}/capacity`, {
    daily_hours: dailyHours, engagement_percent: engagementPercent,
  });
  return data;
};

/** プロジェクトのカレンダー（根の曜日・自分と先祖の休日）と、メンバーの休み（ADR-0058・ADR-0059）。 */
export const teamCalendarKey = (projectId: number) => ['projects', projectId, 'calendar'] as const;

export const getTeamCalendar = async (projectId: number): Promise<TeamCalendar> => {
  const { data } = await client.get<TeamCalendar>(`/projects/${projectId}/calendar`);
  return data;
};

/** 稼働する曜日（管理者だけ。1 つ以上）。 */
export const setTeamWorkdays = async (projectId: number, workdays: WeekdayCode[]): Promise<TeamCalendar> => {
  const { data } = await client.put<TeamCalendar>(`/projects/${projectId}/calendar/workdays`, { workdays });
  return data;
};

/** そのプロジェクトに休日を足す（同じ日なら名前を書き換える。下のプロジェクトにも足せる。管理者だけ）。 */
export const addTeamDayOff = async (projectId: number, day: string, name: string | null): Promise<TeamCalendar> => {
  const { data } = await client.post<TeamCalendar>(`/projects/${projectId}/calendar/days-off`, { day, name });
  return data;
};

export const removeTeamDayOff = async (projectId: number, day: string): Promise<TeamCalendar> => {
  const { data } = await client.delete<TeamCalendar>(`/projects/${projectId}/calendar/days-off/${day}`);
  return data;
};

/** そのプロジェクトに稼働日（稼働しない曜日に働く日）を足す。同じ日の休日は消える（管理者だけ。ADR-0060）。 */
export const addExtraWorkday = async (projectId: number, day: string, name: string | null): Promise<TeamCalendar> => {
  const { data } = await client.post<TeamCalendar>(`/projects/${projectId}/calendar/extra-workdays`, { day, name });
  return data;
};

export const removeExtraWorkday = async (projectId: number, day: string): Promise<TeamCalendar> => {
  const { data } = await client.delete<TeamCalendar>(`/projects/${projectId}/calendar/extra-workdays/${day}`);
  return data;
};

/** その年の日本の祝日を足す（すでにある日はそのまま。管理者だけ）。 */
export const importTeamJapaneseHolidays = async (projectId: number, year: number): Promise<TeamCalendar> => {
  const { data } = await client.post<TeamCalendar>(`/projects/${projectId}/calendar/days-off/japan`, { year });
  return data;
};

/**
 * その人のその日（休み・半休は offPercent、稼働時間を決めるなら hours。同じ日なら書き換える）。
 * 本人か管理者だけ。プロジェクトをまたいで同じ（ADR-0059・ADR-0060）。
 */
export const addMemberLeave = async (
  projectId: number, userId: number, day: string, offPercent = 100, hours: number | null = null,
): Promise<TeamCalendar> => {
  const { data } = await client.post<TeamCalendar>(`/projects/${projectId}/members/${userId}/leave`, {
    day, off_percent: offPercent, hours,
  });
  return data;
};

export const removeMemberLeave = async (projectId: number, userId: number, day: string): Promise<TeamCalendar> => {
  const { data } = await client.delete<TeamCalendar>(`/projects/${projectId}/members/${userId}/leave/${day}`);
  return data;
};
