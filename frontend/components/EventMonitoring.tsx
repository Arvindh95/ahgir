import { useEffect, useState } from 'react'
import { eventService, EventDetails } from '@/lib/events'
import { auditService, AuditLog } from '@/lib/audit'

interface EventMonitoringProps {
  eventId: string
}

export default function EventMonitoring({ eventId }: EventMonitoringProps) {
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([])
  const [isLoadingEvent, setIsLoadingEvent] = useState(true)
  const [isLoadingLogs, setIsLoadingLogs] = useState(true)
  const [error, setError] = useState('')
  const [actionFilter, setActionFilter] = useState<string>('')
  const [isReindexing, setIsReindexing] = useState(false)

  useEffect(() => {
    loadEvent()
    loadAuditLogs()
  }, [eventId, actionFilter])

  const loadEvent = async () => {
    try {
      setIsLoadingEvent(true)
      const data = await eventService.getEvent(eventId)
      setEvent(data)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to load event')
    } finally {
      setIsLoadingEvent(false)
    }
  }

  const loadAuditLogs = async () => {
    try {
      setIsLoadingLogs(true)
      const data = await auditService.getAuditLogs(eventId, 1, 20, actionFilter || undefined)
      setAuditLogs(data.logs)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to load audit logs')
    } finally {
      setIsLoadingLogs(false)
    }
  }

  const handleReindex = async () => {
    if (!confirm('Reindex all photos? This will reset the status of all photos.')) {
      return
    }

    try {
      setIsReindexing(true)
      await eventService.reindexEvent(eventId)
      alert('Reindexing started')
      loadEvent()
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Failed to start reindexing')
    } finally {
      setIsReindexing(false)
    }
  }

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString()
  }

  const getActionColor = (action: string): string => {
    switch (action) {
      case 'scan':
        return '#2196f3'
      case 'upload':
        return '#28a745'
      case 'reindex':
        return '#ff9800'
      case 'delete':
        return '#dc3545'
      default:
        return '#666'
    }
  }

  if (isLoadingEvent) {
    return <p>Loading monitoring data...</p>
  }

  if (error || !event) {
    return (
      <div style={{ color: 'red', padding: '20px', backgroundColor: '#ffebee', borderRadius: '4px' }}>
        {error || 'Failed to load monitoring data'}
      </div>
    )
  }

  return (
    <div>
      {/* Indexing Status Section */}
      <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h2 style={{ margin: 0 }}>Indexing Status</h2>
          <button
            onClick={handleReindex}
            disabled={isReindexing}
            style={{
              backgroundColor: isReindexing ? '#ccc' : '#28a745',
              color: 'white',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '4px',
              cursor: isReindexing ? 'not-allowed' : 'pointer',
            }}
          >
            {isReindexing ? 'Reindexing...' : 'Reindex All'}
          </button>
        </div>

        {/* Progress Bar */}
        <div style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
            <span style={{ fontWeight: 'bold' }}>Indexing Progress</span>
            <span style={{ fontWeight: 'bold' }}>{event.status.indexing_percentage.toFixed(1)}%</span>
          </div>
          <div style={{ width: '100%', height: '24px', backgroundColor: '#e0e0e0', borderRadius: '12px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${event.status.indexing_percentage}%`,
                height: '100%',
                backgroundColor: '#0070f3',
                transition: 'width 0.3s',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'white',
                fontSize: '12px',
                fontWeight: 'bold',
              }}
            >
              {event.status.indexing_percentage > 10 && `${event.status.indexing_percentage.toFixed(0)}%`}
            </div>
          </div>
        </div>

        {/* Photo Counts Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '15px' }}>
          <div style={{ padding: '15px', backgroundColor: '#f5f5f5', borderRadius: '8px', textAlign: 'center' }}>
            <div style={{ fontSize: '32px', fontWeight: 'bold', marginBottom: '5px' }}>
              {event.status.total_photos}
            </div>
            <div style={{ color: '#666', fontSize: '14px' }}>Total Photos</div>
          </div>
          <div style={{ padding: '15px', backgroundColor: '#e8f5e9', borderRadius: '8px', textAlign: 'center' }}>
            <div style={{ fontSize: '32px', fontWeight: 'bold', marginBottom: '5px', color: '#28a745' }}>
              {event.status.indexed}
            </div>
            <div style={{ color: '#666', fontSize: '14px' }}>Indexed</div>
          </div>
          <div style={{ padding: '15px', backgroundColor: '#fff3e0', borderRadius: '8px', textAlign: 'center' }}>
            <div style={{ fontSize: '32px', fontWeight: 'bold', marginBottom: '5px', color: '#ff9800' }}>
              {event.status.pending}
            </div>
            <div style={{ color: '#666', fontSize: '14px' }}>Pending</div>
          </div>
          <div style={{ padding: '15px', backgroundColor: '#f5f5f5', borderRadius: '8px', textAlign: 'center' }}>
            <div style={{ fontSize: '32px', fontWeight: 'bold', marginBottom: '5px' }}>
              {event.status.no_faces}
            </div>
            <div style={{ color: '#666', fontSize: '14px' }}>No Faces</div>
          </div>
          <div style={{ padding: '15px', backgroundColor: '#ffebee', borderRadius: '8px', textAlign: 'center' }}>
            <div style={{ fontSize: '32px', fontWeight: 'bold', marginBottom: '5px', color: '#dc3545' }}>
              {event.status.failed}
            </div>
            <div style={{ color: '#666', fontSize: '14px' }}>Failed</div>
          </div>
          <div style={{ padding: '15px', backgroundColor: '#e3f2fd', borderRadius: '8px', textAlign: 'center' }}>
            <div style={{ fontSize: '32px', fontWeight: 'bold', marginBottom: '5px', color: '#2196f3' }}>
              {event.status.total_faces}
            </div>
            <div style={{ color: '#666', fontSize: '14px' }}>Total Faces</div>
          </div>
        </div>
      </div>

      {/* Audit Logs Section */}
      <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '8px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h2 style={{ margin: 0 }}>Audit Logs</h2>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <label htmlFor="actionFilter" style={{ fontSize: '14px' }}>Filter:</label>
            <select
              id="actionFilter"
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              style={{
                padding: '8px',
                border: '1px solid #ddd',
                borderRadius: '4px',
                fontSize: '14px',
              }}
            >
              <option value="">All Actions</option>
              <option value="access">Access</option>
              <option value="scan">Scan</option>
              <option value="upload">Upload</option>
              <option value="reindex">Reindex</option>
              <option value="delete">Delete</option>
            </select>
          </div>
        </div>

        {isLoadingLogs ? (
          <p>Loading audit logs...</p>
        ) : auditLogs.length === 0 ? (
          <p style={{ textAlign: 'center', color: '#666', padding: '20px' }}>
            No audit logs found
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5', borderBottom: '2px solid #ddd' }}>
                  <th style={{ padding: '12px', textAlign: 'left', fontSize: '14px' }}>Timestamp</th>
                  <th style={{ padding: '12px', textAlign: 'left', fontSize: '14px' }}>Actor</th>
                  <th style={{ padding: '12px', textAlign: 'left', fontSize: '14px' }}>Action</th>
                  <th style={{ padding: '12px', textAlign: 'left', fontSize: '14px' }}>Details</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.map((log) => (
                  <tr key={log.log_id} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '12px', fontSize: '13px' }}>
                      {formatTimestamp(log.timestamp)}
                    </td>
                    <td style={{ padding: '12px', fontSize: '13px' }}>
                      <span style={{
                        padding: '4px 8px',
                        borderRadius: '4px',
                        backgroundColor: log.actor_type === 'admin' ? '#e3f2fd' : '#f3e5f5',
                        fontSize: '12px',
                      }}>
                        {log.actor_type}
                      </span>
                    </td>
                    <td style={{ padding: '12px', fontSize: '13px' }}>
                      <span style={{
                        padding: '4px 8px',
                        borderRadius: '4px',
                        backgroundColor: getActionColor(log.action),
                        color: 'white',
                        fontSize: '12px',
                        fontWeight: 'bold',
                      }}>
                        {log.action}
                      </span>
                    </td>
                    <td style={{ padding: '12px', fontSize: '13px', color: '#666' }}>
                      {log.metadata && Object.keys(log.metadata).length > 0 ? (
                        <span>{JSON.stringify(log.metadata)}</span>
                      ) : (
                        <span>-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
