import client from './client';
import type { Person, Project, ProjectMembers, ProjectRole, ProjectStatus, TeamCalendar, WeekdayCode } from '../types';

/** Projects (task #187, ADR-0024). Writes also invalidate tasks and milestones (their paths change). */
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

/** Change the parent or position among siblings (omitting position = last). 409 when moving under itself. */
export const moveProject = async (
  id: number, parentProjectId: number | null, position?: number,
): Promise<Project> => {
  const { data } = await client.post<Project>(`/projects/${id}/move`, {
    parent_project_id: parentProjectId, position,
  });
  return data;
};

/** Only empty projects can be deleted (409 if not empty). */
export const deleteProject = async (id: number): Promise<void> => {
  await client.delete(`/projects/${id}`);
};

/** People selectable as member or assignee (anyone who has signed in to WBS at least once. ADR-0055). */
export const PEOPLE_KEY = ['projects', 'people'] as const;

export const getPeople = async (): Promise<Person[]> => {
  const { data } = await client.get<Person[]>('/projects/people');
  return data;
};

/** Members of the tree (topmost project). Any level's id returns the root's roster. */
export const projectMembersKey = (projectId: number) => ['projects', projectId, 'members'] as const;

export const getProjectMembers = async (projectId: number): Promise<ProjectMembers> => {
  const { data } = await client.get<ProjectMembers>(`/projects/${projectId}/members`);
  return data;
};

/** Add (or update the role if already a member). Admins only (403). */
export const addProjectMember = async (
  projectId: number, userId: number, role: ProjectRole,
): Promise<ProjectMembers> => {
  const { data } = await client.post<ProjectMembers>(`/projects/${projectId}/members`, { user_id: userId, role });
  return data;
};

/** Change the role. 409 when demoting the last admin. */
export const changeProjectMemberRole = async (
  projectId: number, userId: number, role: ProjectRole,
): Promise<ProjectMembers> => {
  const { data } = await client.put<ProjectMembers>(`/projects/${projectId}/members/${userId}`, { role });
  return data;
};

/** Remove (leave, if self). 409 for the last admin. Assignments remain. */
export const removeProjectMember = async (projectId: number, userId: number): Promise<void> => {
  await client.delete(`/projects/${projectId}/members/${userId}`);
};

/** Daily hours and engagement rate (ADR-0058). Admins for anyone, members only their own (403). */
export const changeProjectMemberCapacity = async (
  projectId: number, userId: number, dailyHours: number, engagementPercent: number,
): Promise<ProjectMembers> => {
  const { data } = await client.put<ProjectMembers>(`/projects/${projectId}/members/${userId}/capacity`, {
    daily_hours: dailyHours, engagement_percent: engagementPercent,
  });
  return data;
};

/** Project calendar (root's weekdays, holidays of self and ancestors) and members' time off (ADR-0058, ADR-0059). */
export const teamCalendarKey = (projectId: number) => ['projects', projectId, 'calendar'] as const;

export const getTeamCalendar = async (projectId: number): Promise<TeamCalendar> => {
  const { data } = await client.get<TeamCalendar>(`/projects/${projectId}/calendar`);
  return data;
};

/** Working weekdays (admins only; at least one). */
export const setTeamWorkdays = async (projectId: number, workdays: WeekdayCode[]): Promise<TeamCalendar> => {
  const { data } = await client.put<TeamCalendar>(`/projects/${projectId}/calendar/workdays`, { workdays });
  return data;
};

/** Add a holiday to the project (renames it on the same day; can be added to sub-projects too; admins only). */
export const addTeamDayOff = async (projectId: number, day: string, name: string | null): Promise<TeamCalendar> => {
  const { data } = await client.post<TeamCalendar>(`/projects/${projectId}/calendar/days-off`, { day, name });
  return data;
};

export const removeTeamDayOff = async (projectId: number, day: string): Promise<TeamCalendar> => {
  const { data } = await client.delete<TeamCalendar>(`/projects/${projectId}/calendar/days-off/${day}`);
  return data;
};

/** Add a working day (work on a non-working weekday) to the project. A holiday on the same day is removed (admins only. ADR-0060). */
export const addExtraWorkday = async (projectId: number, day: string, name: string | null): Promise<TeamCalendar> => {
  const { data } = await client.post<TeamCalendar>(`/projects/${projectId}/calendar/extra-workdays`, { day, name });
  return data;
};

export const removeExtraWorkday = async (projectId: number, day: string): Promise<TeamCalendar> => {
  const { data } = await client.delete<TeamCalendar>(`/projects/${projectId}/calendar/extra-workdays/${day}`);
  return data;
};

/** Add Japan's public holidays for the year (existing days unchanged; admins only). */
export const importTeamJapaneseHolidays = async (projectId: number, year: number): Promise<TeamCalendar> => {
  const { data } = await client.post<TeamCalendar>(`/projects/${projectId}/calendar/days-off/japan`, { year });
  return data;
};

/**
 * That person's day (offPercent for day off / half day, hours to set working hours; overwrites the same day).
 * Only the person or an admin. Shared across projects (ADR-0059, ADR-0060).
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
