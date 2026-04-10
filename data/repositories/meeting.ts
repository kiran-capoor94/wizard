import { prisma } from '../db.js'

/**
 * Returns true if a meeting with the given id exists.
 */
export async function meetingExists(id: number): Promise<boolean> {
  const count = await prisma.meeting.count({ where: { id } })
  return count > 0
}
