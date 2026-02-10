import { motion, useReducedMotion } from 'framer-motion';
import { createContext, useContext } from 'react';

const FadeInStaggerContext = createContext(false);

const viewport = { once: true, margin: '0px 0px -200px' };

export function FadeIn(props: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  direction?: 'up' | 'down' | 'left' | 'right';
  fullWidth?: boolean;
}) {
  const shouldReduceMotion = useReducedMotion();
  const isInStaggerGroup = useContext(FadeInStaggerContext);

  const {
    children,
    className,
    delay = 0,
    direction = 'up',
    fullWidth = false,
  } = props;

  const animationVariants = {
    hidden: { 
      opacity: 0, 
      y: direction === 'up' ? 24 : direction === 'down' ? -24 : 0, 
      x: direction === 'left' ? 24 : direction === 'right' ? -24 : 0 
    },
    visible: { 
      opacity: 1, 
      y: 0, 
      x: 0,
      transition: {
        duration: 0.5,
        ease: [0.21, 0.47, 0.32, 0.98] as const, // Custom smooth ease
        delay: isInStaggerGroup ? 0 : delay,
      },
    },
  };

  return (
    <motion.div
      variants={animationVariants}
      initial={shouldReduceMotion ? 'visible' : 'hidden'}
      whileInView="visible"
      viewport={viewport}
      className={className}
      {...(fullWidth ? { style: { width: '100%' } } : {})}
    >
      {children}
    </motion.div>
  );
}

export function FadeInStagger({
  children,
  faster = false,
  className,
}: {
  children: React.ReactNode;
  faster?: boolean;
  className?: string;
}) {
  return (
    <FadeInStaggerContext.Provider value={true}>
      <motion.div
        initial="hidden"
        whileInView="visible"
        viewport={viewport}
        transition={{ staggerChildren: faster ? 0.12 : 0.2 }}
        className={className}
      >
        {children}
      </motion.div>
    </FadeInStaggerContext.Provider>
  );
}
