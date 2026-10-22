import { useSearchParams } from 'react-router-dom'
import { useAuth } from './auth'
import { journeyLink, readJourney } from './bookingJourney'

export function useBookingJourney() {
  const auth = useAuth()
  const [params] = useSearchParams()
  const owner = auth.user?.uid ?? 'guest'
  const journey = readJourney(owner, params.get('bookingReturn'))
  return {
    owner, journey,
    returnTo: journey ? journeyLink(journey.returnTo, journey.id) : null,
    onward: (path: string) => journey ? journeyLink(path, journey.id) : path,
  }
}
