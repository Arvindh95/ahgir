export function getErrorMessage(err: any, context: string): string {
  if (!err.response) {
    return `Network error: Check your internet connection and try again.`
  }
  const status = err.response.status
  if (status >= 500) {
    return `Server error while ${context}. Please try again in a few moments.`
  }
  if (status === 403) {
    return `You don't have permission to ${context}.`
  }
  if (status === 401) {
    return `Session expired. Please log in again.`
  }
  return err.response?.data?.error?.message || `Failed to ${context}. Please try again.`
}
