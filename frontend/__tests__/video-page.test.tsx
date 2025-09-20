import { render, screen, waitFor } from '@testing-library/react'
import { useParams, useSearchParams, useRouter } from 'next/navigation'
import VideoPage from '@/app/v/[id]/page'

// Mock Next.js hooks
jest.mock('next/navigation', () => ({
  useParams: jest.fn(),
  useSearchParams: jest.fn(),
  useRouter: jest.fn(),
}))

// Mock the shortcuts hook
jest.mock('../src/app/v/[id]/shortcuts', () => ({
  useChapterShortcuts: jest.fn(),
}))

// Mock fetch
global.fetch = jest.fn()

const mockUseParams = useParams as jest.MockedFunction<typeof useParams>
const mockUseSearchParams = useSearchParams as jest.MockedFunction<typeof useSearchParams>
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>
const mockFetch = fetch as jest.MockedFunction<typeof fetch>

describe('Video Page', () => {
  const mockSearchParams = {
    get: jest.fn(),
  }

  const mockRouter = {
    push: jest.fn(),
  }

  beforeEach(() => {
    mockUseParams.mockReturnValue({ id: 'test-video-id' })
    mockUseSearchParams.mockReturnValue(mockSearchParams as any)
    mockUseRouter.mockReturnValue(mockRouter as any)
    mockSearchParams.get.mockReturnValue(null)

    // Reset fetch mock
    mockFetch.mockClear()
  })

  it('renders loading state initially', () => {
    // Mock fetch to never resolve
    mockFetch.mockImplementation(() => new Promise(() => {}))

    render(<VideoPage />)

    expect(screen.getByText('Loading transcript and AI tools…')).toBeInTheDocument()
  })

  it('renders error state when fetch fails', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'))

    render(<VideoPage />)

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument()
    })
  })

  it('renders video content when data loads successfully', async () => {
    const mockTranscriptData = {
      segments: [
        { start: 0, end: 5, text: 'Hello world' },
        { start: 5, end: 10, text: 'This is a test' },
      ],
      text: 'Hello world This is a test',
    }

    const mockSummaryData = {
      summary: 'This is a test video summary',
    }

    const mockChaptersData = {
      chapters: [
        { title: 'Introduction', start: 0 },
        { title: 'Main Content', start: 60 },
      ],
    }

    const mockTakeawaysData = {
      takeaways: ['Learn about testing', 'Understand React'],
    }

    const mockEntitiesData = {
      entities: ['React', 'Testing', 'JavaScript'],
    }

    mockFetch
      .mockResolvedValueOnce({
        json: () => Promise.resolve(mockTranscriptData),
      } as any)
      .mockResolvedValueOnce({
        json: () => Promise.resolve(mockSummaryData),
      } as any)
      .mockResolvedValueOnce({
        json: () => Promise.resolve(mockChaptersData),
      } as any)
      .mockResolvedValueOnce({
        json: () => Promise.resolve(mockTakeawaysData),
      } as any)
      .mockResolvedValueOnce({
        json: () => Promise.resolve(mockEntitiesData),
      } as any)

    render(<VideoPage />)

    await waitFor(() => {
      expect(screen.getByText('TL;DR')).toBeInTheDocument()
    })

    // Check that content is rendered
    expect(screen.getByText('This is a test video summary')).toBeInTheDocument()
    expect(screen.getByText('Chapters')).toBeInTheDocument()
    expect(screen.getByText('Key takeaways')).toBeInTheDocument()
    expect(screen.getByText('Entities')).toBeInTheDocument()
    expect(screen.getByText('Export')).toBeInTheDocument()
  })

  it('renders YouTube iframe with correct video ID', async () => {
    mockFetch.mockResolvedValue({
      json: () => Promise.resolve({
        segments: [],
        text: '',
      }),
    } as any)

    render(<VideoPage />)

    await waitFor(() => {
      const iframe = screen.getByTitle('YouTube video player')
      expect(iframe).toBeInTheDocument()
      expect(iframe).toHaveAttribute('src', 'https://www.youtube.com/embed/test-video-id')
    })
  })

  it('handles timestamp parameter correctly', async () => {
    mockSearchParams.get.mockReturnValue('42')

    mockFetch.mockResolvedValue({
      json: () => Promise.resolve({
        segments: [],
        text: '',
      }),
    } as any)

    render(<VideoPage />)

    await waitFor(() => {
      const iframe = screen.getByTitle('YouTube video player')
      expect(iframe).toHaveAttribute('src', 'https://www.youtube.com/embed/test-video-id?start=42&autoplay=0')
    })
  })

  it('renders transcript segments with clickable timestamps', async () => {
    const mockData = {
      segments: [
        { start: 0, end: 5, text: 'Hello world' },
        { start: 60, end: 65, text: 'One minute mark' },
      ],
      text: 'Hello world One minute mark',
    }

    mockFetch.mockResolvedValue({
      json: () => Promise.resolve(mockData),
    } as any)

    render(<VideoPage />)

    await waitFor(() => {
      expect(screen.getByText('Hello world')).toBeInTheDocument()
      expect(screen.getByText('One minute mark')).toBeInTheDocument()
    })

    // Check timestamp buttons
    expect(screen.getByText('00:00:00')).toBeInTheDocument()
    expect(screen.getByText('00:01:00')).toBeInTheDocument()
  })

  it('renders chapter navigation', async () => {
    const mockChaptersData = {
      chapters: [
        { title: 'Introduction', start: 0 },
        { title: 'Main Content', start: 120 },
        { title: 'Conclusion', start: 300 },
      ],
    }

    mockFetch.mockResolvedValue({
      json: () => Promise.resolve(mockChaptersData),
    } as any)

    render(<VideoPage />)

    await waitFor(() => {
      expect(screen.getByText('00:00:00 — Introduction')).toBeInTheDocument()
      expect(screen.getByText('00:02:00 — Main Content')).toBeInTheDocument()
      expect(screen.getByText('00:05:00 — Conclusion')).toBeInTheDocument()
    })
  })

  it('renders export links with correct URLs', async () => {
    mockFetch.mockResolvedValue({
      json: () => Promise.resolve({
        segments: [],
        text: '',
      }),
    } as any)

    render(<VideoPage />)

    await waitFor(() => {
      const txtLink = screen.getByText('.txt')
      const srtLink = screen.getByText('.srt')
      const vttLink = screen.getByText('.vtt')
      const chaptersLink = screen.getByText('chapters.json')

      expect(txtLink).toHaveAttribute('href', 'http://localhost:8000/api/export/txt/test-video-id')
      expect(srtLink).toHaveAttribute('href', 'http://localhost:8000/api/export/srt/test-video-id')
      expect(vttLink).toHaveAttribute('href', 'http://localhost:8000/api/export/vtt/test-video-id')
      expect(chaptersLink).toHaveAttribute('href', 'http://localhost:8000/api/export/chapters/test-video-id')
    })
  })
})
