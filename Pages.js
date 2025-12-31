import React, { useState } from 'react';
import { base44 } from '@/api/base44Client';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { UserPlus, Save, ArrowRight, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { createPageUrl } from '../utils';
import SuggestFamilyDialog from '../components/alumni/SuggestFamilyDialog';
import { toast } from 'sonner';

export default function AddAlumniPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    phone: '',
    email: '',
    current_city: '',
    current_street: '',
    parent_city: '',
    parent_street: '',
    parent_house_number: '',
    parent_phone: '',
    graduation_year_hebrew: '',
    tags: '',
    notes: ''
  });

  const [savedAlumni, setSavedAlumni] = useState(null);
  const [showSuggestDialog, setShowSuggestDialog] = useState(false);

  const createMutation = useMutation({
    mutationFn: (data) => base44.entities.Alumni.create(data),
    onSuccess: (newAlumni) => {
      queryClient.invalidateQueries(['alumni']);
      setSavedAlumni(newAlumni);