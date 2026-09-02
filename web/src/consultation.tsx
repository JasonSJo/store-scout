import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '../app/globals.css';
import Consultation from '../app/consultation/page';

createRoot(document.getElementById('root')!).render(<StrictMode><Consultation/></StrictMode>);
