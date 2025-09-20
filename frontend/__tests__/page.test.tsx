import { render, screen } from '@testing-library/react'
import Home from '@/app/page'

describe('Home Page', () => {
  it('renders the main heading', () => {
    render(<Home />)

    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading).toBeInTheDocument()
    expect(heading).toHaveTextContent('Paste a YouTube URL above')
  })

  it('renders the description', () => {
    render(<Home />)

    const description = screen.getByText(/Drop-in: replace youtube.com/)
    expect(description).toBeInTheDocument()
  })

  it('has correct layout classes', () => {
    render(<Home />)

    const container = screen.getByRole('heading').closest('div')
    expect(container).toHaveClass('mx-auto', 'max-w-3xl', 'px-4', 'py-20', 'text-center')
  })
})
