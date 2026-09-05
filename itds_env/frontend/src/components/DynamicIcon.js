import React from 'react';
import { HelpCircle, LayoutDashboard, BarChart2, Search, FileText, UploadCloud, Users2, Clock, Volume2, ShieldCheck, Sparkles, LineChart, TrendingUp } from "lucide-react";

const iconMap = {
  LayoutDashboard,
  BarChart2,
  Search,
  FileText,
  UploadCloud,
  Users2,
  Clock,
  Volume2,
  ShieldCheck,
  Sparkles, // For Simplify
  LineChart,  // For Trends
  TrendingUp  // For Analytics
};

const DynamicIcon = React.memo(({ name, size = 18, ...props }) => {
  if (!name || typeof name !== 'string') {
    console.warn('DynamicIcon: invalid name prop', { name, type: typeof name });
    return <HelpCircle size={size} {...props} title="Invalid icon name" />;
  }

  const IconComponent = iconMap[name] || HelpCircle;

  if (!IconComponent) {
    console.warn(`DynamicIcon: Icon "${name}" not found`);
    return <HelpCircle size={size} {...props} title={`Icon ${name} not found`} />;
  }

  return <IconComponent size={size} {...props} />;
});

DynamicIcon.displayName = 'DynamicIcon';

export default DynamicIcon;
