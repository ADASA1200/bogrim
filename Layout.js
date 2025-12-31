import React from 'react';
import { Link } from 'react-router-dom';
import { createPageUrl } from './utils';
import { Users, UserPlus, BarChart3, BookOpen } from 'lucide-react';

export default function Layout({ children, currentPageName }) {
  const navItems = [
    { name: 'Alumni', label: 'בוגרים', icon: Users },
    { name: 'AddAlumni', label: 'הוסף בוגר', icon: UserPlus },
    { name: 'Statistics', label: 'סטטיסטיקות', icon: BarChart3 }
  ];

  return (
    <div dir="rtl" className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      <style>{`
        :root {
          --primary: #1e40af;
          --primary-dark: #1e3a8a;
          --accent: #3b82f6;
          --success: #10b981;
          --warning: #f59e0b;
        }
        
        * {
          font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
      `}</style>

      {/* Header */}
      <header className="bg-white shadow-lg border-b-4 border-blue-600">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="bg-gradient-to-br from-blue-600 to-indigo-700 p-3 rounded-xl shadow-lg">
                <BookOpen className="w-8 h-8 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-800">מערכת ניהול בוגרים</h1>
                <p className="text-sm text-gray-500">ישיבת באר התלמוד</p>
              </div>
            </div>
            