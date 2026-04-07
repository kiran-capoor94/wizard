// integrations/notion/pull.ts
import { Client } from '@notionhq/client'
import { scrub } from '../../security/scrub.js'
import type { ScrubResult } from '../../security/types.js'

export type RawNotionTask = {
  notionId: string
  title: ScrubResult
  description: ScrubResult
  status: string
  dueDate: string | null
  externalTaskId: string | null
}

export type RawNotionActionItem = {
  action: ScrubResult
  dueDate: string | null
}

export type RawNotionMeeting = {
  notionId: string
  title: ScrubResult
  notes: ScrubResult
  date: string | null
  actionItems: RawNotionActionItem[]
}

/**
 * Fetches tasks from a Notion database, scrubs PII from text fields.
 * Returns raw (unsaved) task data with scrub results.
 * Tasks use externalTaskId (not jiraKey) for external ticket references.
 */
export async function pullNotionTasks(
  token: string,
  databaseId: string
): Promise<RawNotionTask[]> {
  // SDK v5 moved databases.query to dataSources.query; cast to any for compatibility
  const notion = new Client({ auth: token }) as any

  const response = await notion.databases.query({ database_id: databaseId })

  return Promise.all(response.results.map(async (page: any) => {
    const props = page.properties ?? {}

    const rawTitle = extractRichText(props['Name'] ?? props['Title']) ?? ''
    const rawDesc = extractRichText(props['Description'] ?? props['Notes']) ?? ''
    const status = extractSelect(props['Status']) ?? 'Todo'
    const dueDate = extractDate(props['Due Date'] ?? props['Due']) ?? null
    const externalTaskId = extractRichText(props['Ticket'] ?? props['External ID']) ?? null

    const [title, description] = await Promise.all([
      scrub(rawTitle, `notion.task.${page.id}.title`),
      scrub(rawDesc, `notion.task.${page.id}.description`),
    ])

    return {
      notionId: page.id,
      title,
      description,
      status,
      dueDate,
      externalTaskId,
    }
  }))
}

/**
 * Fetches meeting notes from a Notion database, scrubs PII from text fields.
 * Action items are returned as separate RawNotionActionItem entries — the caller
 * creates ActionItem records in Postgres (not String[] on Meeting).
 */
export async function pullNotionMeetings(
  token: string,
  databaseId: string
): Promise<RawNotionMeeting[]> {
  // SDK v5 moved databases.query to dataSources.query; cast to any for compatibility
  const notion = new Client({ auth: token }) as any

  const response = await notion.databases.query({ database_id: databaseId })

  return Promise.all(response.results.map(async (page: any) => {
    const props = page.properties ?? {}

    const rawTitle = extractRichText(props['Name'] ?? props['Title']) ?? ''
    const rawNotes = extractRichText(props['Notes'] ?? props['Content']) ?? ''
    const date = extractDate(props['Date'] ?? props['Meeting Date']) ?? null

    const rawActionItems = extractActionItems(props['Action Items'] ?? props['Actions'])

    const actionItems: RawNotionActionItem[] = await Promise.all(
      rawActionItems.map(async (item, idx) => ({
        action: await scrub(item, `notion.meeting.${page.id}.actionItem.${idx}`),
        dueDate: null,
      }))
    )

    const [title, notes] = await Promise.all([
      scrub(rawTitle, `notion.meeting.${page.id}.title`),
      scrub(rawNotes, `notion.meeting.${page.id}.notes`),
    ])

    return {
      notionId: page.id,
      title,
      notes,
      date,
      actionItems,
    }
  }))
}

// --- Notion property extractors ---

function extractRichText(prop: any): string | undefined {
  if (!prop) return undefined
  if (prop.type === 'rich_text') {
    return prop.rich_text?.map((r: any) => r.plain_text).join('') ?? ''
  }
  if (prop.type === 'title') {
    return prop.title?.map((r: any) => r.plain_text).join('') ?? ''
  }
  return undefined
}

function extractSelect(prop: any): string | undefined {
  if (!prop) return undefined
  return prop.select?.name
}

function extractDate(prop: any): string | undefined {
  if (!prop) return undefined
  return prop.date?.start
}

function extractActionItems(prop: any): string[] {
  if (!prop) return []
  if (prop.type === 'rich_text') {
    const text = prop.rich_text?.map((r: any) => r.plain_text).join('') ?? ''
    return text.split(/\n|•|—/).map((s: string) => s.trim()).filter(Boolean)
  }
  if (prop.type === 'multi_select') {
    return prop.multi_select?.map((s: any) => s.name) ?? []
  }
  return []
}
